"""Emulate only packet builders from the original binary; stop before any USB I/O.
Requires pefile and unicorn, only for protocol verification, not normal use.
"""
from pathlib import Path
import json,struct
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX,UC_X86_REG_ESP
ROOT=Path(__file__).resolve().parents[1]
PE=pefile.PE(str(ROOT/'research/extracted/app/HATOR_Pulsar3_Software.exe'))

def capture(address,args=(),payload=None):
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x200000);u.mem_write(0x400000,PE.get_memory_mapped_image())
 u.mem_map(0x1000000,0x100000);obj=0x1010000;data=0x1020000;stack=0x10f0000
 u.mem_write(obj+0x1c,b'\x01');u.reg_write(UC_X86_REG_ECX,obj)
 if payload is not None:u.mem_write(data,bytes(payload))
 vals=[data if x=='data' else x for x in args]
 u.mem_write(stack,struct.pack('<'+'I'*(len(vals)+1),0x10ff000,*vals));u.reg_write(UC_X86_REG_ESP,stack)
 result={}
 def hook(uc,addr,size,_):
  if addr==0x404e80:
   sp=uc.reg_read(UC_X86_REG_ESP);count,wait=struct.unpack('<II',uc.mem_read(sp+4,8))
   result.update(header=bytes(uc.mem_read(obj+0x28,9)).hex(),payload=bytes(uc.mem_read(obj+0x3a,count)).hex(),wait=wait)
   uc.emu_stop()
 u.hook_add(UC_HOOK_CODE,hook)
 u.emu_start(address,0x10ff000,count=100000)
 if not result:raise RuntimeError('Builder did not reach send function')
 return result

if __name__=='__main__':
 vectors={
 'sync':capture(0x407450),
 'parameters0_profile0':capture(0x405b60,('data',0),bytes(range(64))),
 'parameters0_profile3':capture(0x405b60,('data',3),bytes(range(64))),
 'parameters1_mask1':capture(0x405860,('data',1),bytes(range(192))),
 'parameters1_mask7':capture(0x405860,('data',7),bytes(range(192))),
 'macro_slot0':capture(0x405560,(0,'data'),bytes(range(128))),
 'macro_slot11':capture(0x405560,(11,'data'),bytes(range(128))),
 'dpi_stage2':capture(0x4069f0,(2,)),
 }
 out=ROOT/'research/reference-packets.json';out.write_text(json.dumps(vectors,indent=2)+'\n')
 for name,v in vectors.items():print(name,v['header'],len(bytes.fromhex(v['payload'])))

def convert_parameter1(payload):
    """Execute the original conversion loop on a complete QML payload."""
    from unicorn.x86_const import UC_X86_REG_EBP,UC_X86_REG_ESI
    if len(payload)!=192:raise ValueError('192 UI bytes required')
    u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x200000);u.mem_write(0x400000,PE.get_memory_mapped_image())
    u.mem_map(0x1000000,0x100000);bp=0x10f0000
    u.reg_write(UC_X86_REG_EBP,bp);u.reg_write(UC_X86_REG_ESP,bp-0x1000);u.reg_write(UC_X86_REG_ESI,0)
    u.mem_write(bp-0xd8,bytes(payload))
    u.emu_start(0x412de2,0x412e8e,count=10000)
    return bytes(u.mem_read(bp-0xd8,192))


def capture_keys(keys):
    """Execute the original button conversion loop, stopping before transmission."""
    if len(keys)!=16:raise ValueError('16 key entries required')
    return convert_parameter1(bytes(128)+bytes(v for key in keys for v in key))[128:]
