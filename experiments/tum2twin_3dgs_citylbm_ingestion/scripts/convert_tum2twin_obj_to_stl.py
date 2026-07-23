#!/usr/bin/env python3
"""Convert a TUM2TWIN OBJ mesh to binary STL in local and z0 coordinates."""
import argparse, json, struct, math, hashlib, time
from pathlib import Path

def md5(path):
    h=hashlib.md5()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest().upper()

def parse_idx(token, vertex_count):
    i=int(token.split('/')[0])
    return i if i > 0 else vertex_count + i + 1

def normal(p0,p1,p2):
    ux,uy,uz=p1[0]-p0[0],p1[1]-p0[1],p1[2]-p0[2]
    vx,vy,vz=p2[0]-p0[0],p2[1]-p0[1],p2[2]-p0[2]
    nx,ny,nz=uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    l=math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.0,0.0,0.0) if l == 0 else (nx/l,ny/l,nz/l)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--out-local', required=True)
    ap.add_argument('--out-z0', required=True)
    ap.add_argument('--manifest', required=True)
    args=ap.parse_args()
    obj=Path(args.obj); out_local=Path(args.out_local); out_z0=Path(args.out_z0)
    out_local.parent.mkdir(parents=True, exist_ok=True); out_z0.parent.mkdir(parents=True, exist_ok=True)
    start=time.time(); vertices=[None]; tri_count=0; bbox_min=[float('inf')]*3; bbox_max=[float('-inf')]*3
    with obj.open('r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('v '):
                _,x,y,z,*_=line.split(); p=(float(x),float(y),float(z)); vertices.append(p)
                for i,v in enumerate(p): bbox_min[i]=min(bbox_min[i],v); bbox_max[i]=max(bbox_max[i],v)
            elif line.startswith('f '):
                n=len(line.split())-1
                if n >= 3: tri_count += n-2
    zshift=-bbox_min[2]
    def header(label):
        b=label.encode('ascii', 'ignore')[:80]
        return b + b' '*(80-len(b))
    with out_local.open('wb') as fl, out_z0.open('wb') as fz:
        fl.write(header('TUM2TWIN local STL')); fz.write(header('TUM2TWIN z0 STL for FluidX3D'))
        fl.write(struct.pack('<I', tri_count)); fz.write(struct.pack('<I', tri_count))
        written=0
        with obj.open('r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if not line.startswith('f '): continue
                ids=[parse_idx(t, len(vertices)-1)-1 for t in line.split()[1:]]
                for j in range(1, len(ids)-1):
                    p0,p1,p2=vertices[ids[0]],vertices[ids[j]],vertices[ids[j+1]]
                    n=normal(p0,p1,p2)
                    fl.write(struct.pack('<12fH', *(n+p0+p1+p2), 0))
                    q0,q1,q2=(p0[0],p0[1],p0[2]+zshift),(p1[0],p1[1],p1[2]+zshift),(p2[0],p2[1],p2[2]+zshift)
                    fz.write(struct.pack('<12fH', *(n+q0+q1+q2), 0))
                    written += 1
    manifest={'obj':str(obj),'out_local':str(out_local),'out_z0':str(out_z0),'vertices':len(vertices)-1,'triangles':written,'bbox_min':bbox_min,'bbox_max':bbox_max,'z_shift':zshift,'md5_local':md5(out_local),'md5_z0':md5(out_z0),'elapsed_seconds':time.time()-start}
    Path(args.manifest).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))
if __name__ == '__main__': main()
