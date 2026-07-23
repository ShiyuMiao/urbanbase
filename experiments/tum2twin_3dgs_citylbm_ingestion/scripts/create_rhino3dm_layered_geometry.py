#!/usr/bin/env python3
"""Create a Rhino 3DM layered geometry file from a TUM2TWIN OBJ mesh.

Note: rhino3dm 8.x can write mesh geometry, materials, layers, and user strings,
but it does not expose a raw OBJ vt-to-3DM UV writer. Use the OBJ/MTL/JPG source
for accurate textured visualization in Rhino.
"""
import argparse, json, hashlib, time
from pathlib import Path
import rhino3dm

def md5(path):
    h=hashlib.md5()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest().upper()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--texture', required=True)
    ap.add_argument('--mtl', required=True)
    ap.add_argument('--out-3dm', required=True)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--layer-name', default='TUM2TWIN::UAS_Photogrammetry_Mesh::material')
    args=ap.parse_args()
    start=time.time(); obj=Path(args.obj); mesh=rhino3dm.Mesh(); bbox_min=[float('inf')]*3; bbox_max=[float('-inf')]*3; v_count=vt_count=tri_faces=0
    with obj.open('r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('v '):
                _,x,y,z,*_=line.split(); p=(float(x),float(y),float(z)); mesh.Vertices.Add(*p); v_count += 1
                for i,v in enumerate(p): bbox_min[i]=min(bbox_min[i],v); bbox_max[i]=max(bbox_max[i],v)
            elif line.startswith('vt '): vt_count += 1
            elif line.startswith('f '):
                ids=[int(t.split('/')[0])-1 for t in line.split()[1:]]
                for j in range(1, len(ids)-1): mesh.Faces.AddFace(ids[0],ids[j],ids[j+1]); tri_faces += 1
    try: mesh.Normals.ComputeNormals()
    except Exception: pass
    model=rhino3dm.File3dm(); layer_index=model.Layers.AddLayer(args.layer_name, (28,120,173,255))
    mat=rhino3dm.Material(); mat.Name='TUM_Downtown_Photogrammetry_Texture_reference'
    try: mat.SetBitmapTexture(str(Path(args.texture)))
    except Exception as e: mat.SetUserString('bitmap_texture_set_error', repr(e))
    mat.SetUserString('texture_accuracy_note', 'Exact OBJ vt UV atlas is not embedded; import OBJ/MTL/JPG for accurate textured visualization.')
    mat_index=model.Materials.Add(mat)
    attrs=rhino3dm.ObjectAttributes(); attrs.Name='TUM_Downtown_Photogrammetry_20241217_fullres_mesh'; attrs.LayerIndex=layer_index; attrs.MaterialIndex=mat_index
    attrs.MaterialSource=rhino3dm.ObjectMaterialSource.MaterialFromObject; attrs.SetUserString('source_obj', str(obj)); attrs.SetUserString('source_mtl', str(Path(args.mtl))); attrs.SetUserString('source_texture', str(Path(args.texture)))
    attrs.SetUserString('texture_note', 'Layered geometry only; use OBJ for accurate texture UVs.')
    model.Objects.AddMesh(mesh, attrs); out=Path(args.out_3dm); out.parent.mkdir(parents=True, exist_ok=True); ok=model.Write(str(out), 7)
    manifest={'write_ok':bool(ok),'out_3dm':str(out),'md5':md5(out) if out.exists() else None,'layer_name':args.layer_name,'vertices':v_count,'texture_coordinates_in_obj':vt_count,'triangles':tri_faces,'bbox_min':bbox_min,'bbox_max':bbox_max,'elapsed_seconds':time.time()-start,'texture_status':'texture referenced; exact UV not embedded'}
    Path(args.manifest).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))
if __name__ == '__main__': main()
