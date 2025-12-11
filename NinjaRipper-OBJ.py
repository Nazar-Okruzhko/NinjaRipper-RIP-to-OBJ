import struct
import sys
import os
import traceback

DEBUG_MODE = False  # Set False to disable block address printing
FLIP_UV_VERTICALLY = True  # Set True to flip V coordinate (1.0 - v)

# UV offset mapping: stride -> bytes to skip after vertex data to reach UV coords
UV_OFFSET_MAP = {
    184: 60,
    56: 48,
    160: 52,
    #...
}

def safe_read(f, size, desc=""):
    data = f.read(size)
    if len(data) != size:
        raise EOFError(f"Unexpected end of file while reading {desc} ({len(data)}/{size} bytes)")
    return data

def read_int32(f):
    return struct.unpack("<I", safe_read(f, 4, "int32"))[0]

def read_float(f):
    return struct.unpack("<f", safe_read(f, 4, "float"))[0]

def find_dds_textures(f):
    """Find first 3 DDS texture filenames in the file"""
    f.seek(0, 0)
    data = f.read()
    pattern = b'.dds\x00'
    
    textures = []
    search_pos = 0
    
    while len(textures) < 3:
        pos = data.find(pattern, search_pos)
        if pos == -1:
            break
        
        # Walk backwards to find the start of the filename
        start = pos
        while start > 0 and data[start - 1] not in [0x00, 0xFF]:
            start -= 1
        
        # Extract the texture filename
        texture_name = data[start:pos + 4].decode('ascii', errors='ignore')
        if texture_name and texture_name not in textures:
            textures.append(texture_name)
            print(f"Found texture #{len(textures)}: {texture_name}")
        
        search_pos = pos + len(pattern)
    
    return textures

def find_last_dds(f):
    f.seek(0, 0)
    data = f.read()
    pattern = b'\x2E\x64\x64\x73\x00'
    last_pos = data.rfind(pattern)
    if last_pos == -1:
        raise ValueError("Pattern '.dds\\x00' not found in file")
    f.seek(last_pos + len(pattern), 0)
    return f.tell()

def write_mtl_file(mtl_path, obj_basename, textures):
    """Write MTL file with embedded texture references"""
    try:
        with open(mtl_path, "w", encoding="utf-8") as mtl:
            mtl.write("# Blender 3.6.23")
            mtl.write("# www.blender.org\n\n")
            mtl.write(f"newmtl {obj_basename}\n")
            mtl.write("Ns 250.000000\n")
            mtl.write("Ka 1.000000 1.000000 1.000000\n")
            mtl.write("Ke 0.000000 0.000000 0.000000\n")
            mtl.write("Ni 1.450000\n")
            mtl.write("d 1.000000\n")
            mtl.write("illum 2\n")
            
            # First DDS: Diffuse map
            if len(textures) >= 1:
                mtl.write(f"map_Kd {textures[0]}\n")
            
            # Third DDS: Specular map
            if len(textures) >= 3:
                mtl.write(f"map_Ks {textures[2]}\n")
            
            # Second DDS: Normal/Bump map
            if len(textures) >= 2:
                mtl.write(f"\nmap_Bump -bm 1.000000 {textures[1]}\n")
        
        print(f"✓ Wrote MTL: {mtl_path}")
    except Exception as e:
        print(f"❌ ERROR writing MTL file: {e}")

def convert_rip_to_obj(input_path):
    print(f"Processing: {input_path}\n")
    
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, base_name + ".obj")
    mtl_path = os.path.join(output_dir, base_name + ".mtl")

    vertices, normals, uvs, faces = [], [], [], []
    textures = []

    try:
        with open(input_path, "rb") as f:

            # --- FIND TEXTURES ---
            print("Searching for DDS textures...")
            textures = find_dds_textures(f)
            if textures:
                print(f"Found {len(textures)} texture(s)\n")
            else:
                print("⚠ No textures found\n")

            # --- HEADER ---
            f.seek(0, 0)
            header_magic = safe_read(f, 8, "Header Magic")
            print(f"Header Magic: {header_magic.hex().upper()}")

            f.seek(0x8)
            face_count = read_int32(f)
            f.seek(0xC)
            vert_count = read_int32(f)
            f.seek(0x10)
            stride = read_int32(f)

            print(f"Faces = {face_count}, Vertex count = {vert_count}, Stride = {stride}")

            # Check if we have UV offset mapping for this stride
            uv_offset = UV_OFFSET_MAP.get(stride)
            if uv_offset is not None:
                uv_stride = stride + 4
                print(f"UV Coord Stride = {uv_stride} (Vertex Stride {stride} + 4 bytes)")
            else:
                print(f"⚠ Warning: No UV offset mapping for stride {stride}. UVs will not be extracted.")
                uv_offset = None

            # --- FACE START ---
            face_start = find_last_dds(f)
            print(f"Starting face extraction at 0x{face_start:08X}")

            # --- FACES ---
            f.seek(face_start, 0)
            for _ in range(face_count):
                i1 = read_int32(f)
                i2 = read_int32(f)
                i3 = read_int32(f)
                # OBJ indices are 1-based
                faces.append((i1 + 1, i2 + 1, i3 + 1))

            # --- VERTEX DATA ---
            vertex_data_start = f.tell()
            for i in range(vert_count):
                vertex_block_start = vertex_data_start + i * stride
                f.seek(vertex_block_start)

                if DEBUG_MODE:
                    print(f"[VERTEX BLOCK ADDRESS] Vertex {i}: 0x{vertex_block_start:08X}")

                # --- Vertex positions ---
                vx = read_float(f)
                vy = read_float(f)
                vz = read_float(f)
                vertices.append((vx, vy, vz))

                # --- Normals (assume right after vertex) ---
                normal_block_start = f.tell()
                nx = read_float(f)
                ny = read_float(f)
                nz = read_float(f)
                normals.append((nx, ny, nz))

                if DEBUG_MODE:
                    print(f"[NORMAL BLOCK ADDRESS] Vertex {i}: 0x{normal_block_start:08X}")

                # --- UV Coordinates ---
                if uv_offset is not None:
                    uv_block_start = vertex_block_start + uv_offset
                    f.seek(uv_block_start)
                    
                    if DEBUG_MODE:
                        print(f"[UV COORD BLOCK ADDRESS] Vertex {i}: 0x{uv_block_start:08X}")
                    
                    u = read_float(f)
                    v = read_float(f)
                    
                    # Flip V coordinate if enabled
                    if FLIP_UV_VERTICALLY:
                        v = 1.0 - v
                    
                    uvs.append((u, v))

            print(f"\nExtracted {len(vertices)} vertices, {len(normals)} normals", end="")
            if uvs:
                print(f", and {len(uvs)} UV coordinates.")
            else:
                print(".")

    except Exception as e:
        print("\n❌ WARNING – Converter crashed while reading:")
        print(type(e).__name__, ":", e)
        traceback.print_exc()
        print("\nAttempting to write out whatever was read so far...")

    # --- WRITE MTL FILE ---
    if textures:
        write_mtl_file(mtl_path, base_name, textures)

    # --- WRITE OBJ ---
    try:
        with open(output_path, "w", encoding="utf-8") as out:
            out.write("# RIP → OBJ\n")
            
            # Reference MTL file if textures were found
            if textures:
                out.write(f"mtllib {base_name}.mtl\n")
            
            for v in vertices:
                out.write(f"v {v[0]} {v[1]} {v[2]}\n")
            
            if uvs:
                for uv in uvs:
                    out.write(f"vt {uv[0]} {uv[1]}\n")
            
            for vn in normals:
                out.write(f"vn {vn[0]} {vn[1]} {vn[2]}\n")
            
            # Use material if textures were found
            if textures:
                out.write(f"usemtl {base_name}\n")
            
            # Write faces with proper format
            for a, b, c in faces:
                if uvs:
                    out.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")  # v/vt/vn format
                else:
                    out.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")  # v//vn format (no UVs)
        
        print(f"✓ Wrote OBJ: {output_path}\n")
    except Exception as e:
        print("\n❌ ERROR writing OBJ file:", e)

# --- MAIN WRAPPER ---
if __name__ == "__main__":
    try:
        if len(sys.argv) <= 1:
            print("Drag .RIP files onto this script.")
            input("Press Enter to exit...")
            sys.exit()

        for arg in sys.argv[1:]:
            if os.path.isfile(arg):
                convert_rip_to_obj(arg)
            else:
                print(f"Skipping: {arg} (not a file)")

    except Exception as e:
        print("\n❌ CRITICAL ERROR – Converter crashed safely:")
        print(type(e).__name__, ":", e)
        traceback.print_exc()
        input("\nPress Enter to exit...")

    print("\nDone. Press Enter to exit.")
    input()
