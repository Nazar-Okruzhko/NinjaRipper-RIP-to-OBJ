import sys
import os
import re
from struct import unpack

def read_uint(fh):
    return unpack('I', fh.read(4))[0]

def read_string(fh):
    str_bytes = b''
    while True:
        c = fh.read(1)
        if c == b'\0' or not c:
            return str_bytes.decode('cp437')
        str_bytes += c

class RipFileAttribute:
    def __init__(self, fh):
        self.semantic = read_string(fh)
        self.semantic_index = read_uint(fh)
        self.offset = read_uint(fh)
        self.size = read_uint(fh)
        self.end = self.offset + self.size
        self.items = read_uint(fh)
        format_codes = ['f', 'I', 'i']  # 0=float, 1=uint, 2=int
        self.format = ''
        for _ in range(self.items):
            id_val = read_uint(fh)
            self.format += format_codes[id_val] if id_val <= 2 else 'I'
        self.data = []

    def parse_vertex(self, buffer):
        self.data.append(unpack(self.format, buffer[self.offset:self.end]))

    def as_floats(self, arity=4, divisor=1.0):
        if self.format.startswith('f' * min(arity, self.items)):
            return [v[:arity] for v in self.data]
        else:
            return [tuple(float(v) / divisor for v in item[:arity]) for item in self.data]

class RipFile:
    def __init__(self, filename):
        self.filename = filename
        self.faces = []
        self.attributes = []
        self.num_verts = 0
        self.textures = []  # Stored but not used in .obj export

    def parse_file(self):
        with open(self.filename, "rb") as fh:
            magic = read_uint(fh)
            if magic != 0xDEADC0DE:
                raise RuntimeError(f"Invalid file magic: {magic:08x}")
            version = read_uint(fh)
            if version != 4:
                raise RuntimeError(f"Invalid file version: {version}")
            num_faces = read_uint(fh)
            self.num_verts = read_uint(fh)
            block_size = read_uint(fh)
            num_tex = read_uint(fh)
            num_shaders = read_uint(fh)  # Ignored
            num_attrs = read_uint(fh)

            for _ in range(num_attrs):
                self.attributes.append(RipFileAttribute(fh))

            for _ in range(num_tex):
                self.textures.append(read_string(fh))

            for _ in range(num_shaders):
                read_string(fh)  # Skip shaders

            for _ in range(num_faces):
                face = unpack('III', fh.read(12))
                if face[0] != face[1] and face[1] != face[2] and face[0] != face[2]:
                    self.faces.append(face)

            for _ in range(self.num_verts):
                data = fh.read(block_size)
                if len(data) != block_size:
                    raise RuntimeError("Incomplete vertex data read")
                for attr in self.attributes:
                    attr.parse_vertex(data)

    def find_attrs(self, semantic):
        return [attr for attr in self.attributes if attr.semantic == semantic]

    def get_vertices(self):
        pos_attrs = self.find_attrs('POSITION')
        if not pos_attrs and self.attributes:
            pos_attrs = [self.attributes[0]]  # Fallback to first attr if available
        return pos_attrs[0].as_floats(3) if pos_attrs else []

    def get_normals(self, divisor=255):
        norm_attrs = self.find_attrs('NORMAL')
        return norm_attrs[0].as_floats(3, divisor) if norm_attrs else None

    def get_uvs(self, divisor=255):
        uv_attrs = self.find_attrs('TEXCOORD')
        if not uv_attrs:
            return None
        # Take first UV map only (ignore multi-maps for .obj)
        first_uv_attr = uv_attrs[0]
        uvs = [(u, 1.0 - v) for u, v in first_uv_attr.as_floats(4, divisor)]
        return uvs

def convert_rip_to_obj(rip_file_path):
    try:
        print(f"Processing {rip_file_path}...")
        rip = RipFile(rip_file_path)
        rip.parse_file()

        vertices = rip.get_vertices()
        normals = rip.get_normals()
        uvs = rip.get_uvs()
        faces = rip.faces

        if not vertices or not faces:
            print(f"Skipping {rip_file_path}: No valid vertices or faces.")
            return

        obj_path = os.path.splitext(rip_file_path)[0] + '.obj'
        with open(obj_path, 'w') as obj_file:
            obj_file.write(f"# Converted from {os.path.basename(rip_file_path)} using standalone .rip to .obj converter\n")

            # Vertices
            for v in vertices:
                obj_file.write(f"v {' '.join(f'{c:.6f}' for c in v)}\n")

            # UVs (if available)
            if uvs:
                for uv in uvs:
                    obj_file.write(f"vt {' '.join(f'{c:.6f}' for c in uv)}\n")

            # Normals (if available)
            if normals:
                for n in normals:
                    obj_file.write(f"vn {' '.join(f'{c:.6f}' for c in n)}\n")

            # Faces (adjust for 1-based indexing; include vt/vn if present)
            for f in faces:
                face_str = ' '.join(str(idx + 1) for idx in f)
                if uvs and normals:
                    face_str = ' '.join(f"{idx+1}/{idx+1}/{idx+1}" for idx in f)
                elif uvs:
                    face_str = ' '.join(f"{idx+1}/{idx+1}" for idx in f)
                elif normals:
                    face_str = ' '.join(f"{idx+1}//{idx+1}" for idx in f)
                obj_file.write(f"f {face_str}\n")

        print(f"Converted {rip_file_path} to {obj_path}")
    except Exception as e:
        print(f"Error processing {rip_file_path}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py file1.rip [file2.rip ...]")
    else:
        for arg in sys.argv[1:]:
            if arg.lower().endswith('.rip') and os.path.isfile(arg):
                convert_rip_to_obj(arg)
            else:
                print(f"Skipping invalid file: {arg}")
