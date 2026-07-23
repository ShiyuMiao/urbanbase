#!/usr/bin/env python3
"""Read a Rhino 3DM and report layer/object/mesh counts."""
import argparse, json
from pathlib import Path
import rhino3dm

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('path'); ap.add_argument('--out')
    args=ap.parse_args(); model=rhino3dm.File3dm.Read(args.path)
    info={'read_ok': model is not None, 'layers': [], 'objects': 0, 'meshes': []}
    if model:
        for i, layer in enumerate(model.Layers): info['layers'].append({'index':i,'name':layer.Name,'full_path':layer.FullPath})
        for obj in model.Objects:
            info['objects'] += 1; g=obj.Geometry
            if isinstance(g, rhino3dm.Mesh): info['meshes'].append({'name':obj.Attributes.Name,'layer_index':obj.Attributes.LayerIndex,'vertices':len(g.Vertices),'faces':len(g.Faces)})
    text=json.dumps(info, indent=2); print(text)
    if args.out: Path(args.out).write_text(text, encoding='utf-8')
if __name__ == '__main__': main()
