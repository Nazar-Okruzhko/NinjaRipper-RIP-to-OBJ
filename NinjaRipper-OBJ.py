import struct
import sys
import os
import traceback

def safe_read(f, size, desc=""):
    data = f.read(size)
    if len(data) != size:
        raise EOFError(f"Unexpected end of file while reading {desc} ({len(data)}/{size} bytes)")
    return data

def read_int16(f):
    return struct.unpack("<h", safe_read(f, 2, "int16"))[0]

def read_int32(f):
    return struct.unpack("<i", safe_read(f, 4, "int32"))[0]

def read_float(f):
    return struct.unpack("<f", safe_read(f, 4, "float"))[0]

def convert_rip_to_obj(input_path):
    print(f"\n=== Processing: {input_path} ===")
    output_path = os.path.splitext(input_path)[0] + ".obj"

    vertices = []
    normals = []
    uvs = []
    faces = []

    try:
        with open(input_path, "rb") as f:

            def logpos(label=""):
                print(f"[DEBUG] Pos=0x{f.tell():08X} {label}")

            # HEADER
            f.seek(8, 0)
            face_count = read_int16(f)
            f.seek(2, 1)
            vert_count = read_int16(f)
            f.seek(621, 1)

            print(f"Faces = {face_count}, Vertex blocks = {vert_count}")

            # FACES
            for _ in range(face_count):
                i1 = read_int32(f)
                i2 = read_int32(f)
                i3 = read_int32(f)
                faces.append((i1 + 1, i2 + 1, i3 + 1))  # OBJ is 1-indexed



            for i in range(vert_count):
                vertex_offset = f.tell()
                print(f"[VERTEX BLOCK ADDRESS] Vertex {i}: 0x{vertex_offset:08X}")

                # Vertex
                vx = read_float(f)
                vy = read_float(f)
                vz = read_float(f)
                vertices.append((vx, vy, vz))

                # Normal
                normal_offset = f.tell()
                print(f"[NORMAL BLOCK ADDRESS] Vertex {i}: 0x{normal_offset:08X}")
                nx = read_float(f)
                ny = read_float(f)
                nz = read_float(f)
                normals.append((nx, ny, nz))
                f.seek(36, 1)

                # UV
                uv_offset = f.tell()
                print(f"[UV BLOCK ADDRESS] Vertex {i}: 0x{uv_offset:08X}")
                u = read_float(f)
                v = read_float(f)
                uvs.append((u, 1.0 - v))  # flip V for OBJ

                # Skip remaining bytes to next vertex block
                f.seek(116, 1)

    except Exception as e:
        print("\n❌ WARNING — Converter crashed while reading:")
        print(type(e).__name__, ":", e)
        traceback.print_exc()
        print("\nAttempting to write out whatever was read so far...")

    # WRITE OBJ file (even if crashed)
    try:
        with open(output_path, "w", encoding="utf-8") as out:
            out.write("# RIP → OBJ\n")
            for v in vertices:
                out.write(f"v {v[0]} {v[1]} {v[2]}\n")
            for vt in uvs:
                out.write(f"vt {vt[0]} {vt[1]}\n")
            for vn in normals:
                out.write(f"vn {vn[0]} {vn[1]} {vn[2]}\n")
            for a, b, c in faces:
                out.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")
        print(f"\n✓ Wrote OBJ: {output_path}\n")
    except Exception as e:
        print("\n❌ ERROR writing OBJ file:", e)

# MAIN WRAPPER
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
        print("\n❌ CRITICAL ERROR — Converter crashed safely:")
        print(type(e).__name__, ":", e)
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")

    print("\nDone. Press Enter to exit.")
    input()
