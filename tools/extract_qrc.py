"""Extract Qt4 resources from the supplied HATOR executable (analysis only)."""
import struct,zlib
from pathlib import Path
import pefile
root=Path(__file__).resolve().parents[1]
pe=pefile.PE(str(root/'research/extracted/app/HATOR_Pulsar3_Software.exe'))
mem=pe.get_memory_mapped_image(); base=pe.OPTIONAL_HEADER.ImageBase
out=root/'research/qrc'
for tree,names,data in [(0x42f8e0,0x42f9a0,0x42fae0),(0x4332e0,0x433460,0x4337a0),(0x441840,0x442440,0x443ac0)]:
 def walk(i,path):
  pos=tree-base+i*14
  no,flags=struct.unpack_from('>IH',mem,pos)
  np=names-base+no
  n=struct.unpack_from('>H',mem,np)[0]
  name=mem[np+6:np+6+2*n].decode('utf-16-be') if i else ''
  p=path/name
  if flags&2:
   count,start=struct.unpack_from('>II',mem,pos+6)
   for j in range(start,start+count): walk(j,p)
  else:
   off=struct.unpack_from('>I',mem,pos+10)[0]+data-base
   size=struct.unpack_from('>I',mem,off)[0]
   blob=mem[off+4:off+4+size]
   if flags&1: blob=zlib.decompress(blob[4:])
   p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(blob)
 walk(0,out)
print('Extracted',len(list(out.rglob('*'))),'resources')
