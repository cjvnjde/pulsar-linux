"""Linux USBFS transport. Claims only configuration interface 2; no driver detach."""
import ctypes
import fcntl
import os
from pathlib import Path
import select
import time
from .protocol import sync_packet,decode_status

class Control(ctypes.Structure):
    _fields_=[('request_type',ctypes.c_uint8),('request',ctypes.c_uint8),
              ('value',ctypes.c_uint16),('index',ctypes.c_uint16),
              ('length',ctypes.c_uint16),('timeout',ctypes.c_uint32),('data',ctypes.c_void_p)]
class Bulk(ctypes.Structure):
    _fields_=[('endpoint',ctypes.c_uint32),('length',ctypes.c_uint32),
              ('timeout',ctypes.c_uint32),('data',ctypes.c_void_p)]
LIBC=ctypes.CDLL(None,use_errno=True)
LIBC.ioctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_void_p]
LIBC.ioctl.restype=ctypes.c_int

def ioctl(fd,command,arg):
    result=LIBC.ioctl(fd,command,ctypes.byref(arg))
    if result<0: raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
    return result

def discover():
    found=[]
    for p in Path('/sys/bus/usb/devices').iterdir():
        try:
            if (p/'idVendor').read_text().strip()!='379a' or (p/'idProduct').read_text().strip()!='3910':continue
            bus=int((p/'busnum').read_text());dev=int((p/'devnum').read_text())
            status_nodes=list(p.glob('*:1.1/*/hidraw/hidraw*'))
            found.append({'sysfs':str(p),'usb':f'/dev/bus/usb/{bus:03d}/{dev:03d}',
                          'status_hidraw':'/dev/'+status_nodes[0].name if len(status_nodes)==1 else None,
                          'usb_id':'379a:3910','product':(p/'product').read_text().strip()})
        except FileNotFoundError:continue
    if len(found)!=1: raise RuntimeError(f'Expected one HATOR Pulsar 3 (379a:3910), found {len(found)}')
    return found[0]

class Mouse:
    def __init__(self): self.info=discover();self.fd=None;self.status_fd=None;self.claimed=False
    def __enter__(self):
        try:
            self.fd=os.open(self.info['usb'],os.O_RDWR)
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if not self.info['status_hidraw']: raise RuntimeError('Vendor status interface was not found')
            self.status_fd=os.open(self.info['status_hidraw'],os.O_RDONLY|os.O_NONBLOCK)
            if (Path(self.info['sysfs'])/(Path(self.info['sysfs']).name+':1.2')/'driver').exists():
                raise RuntimeError('Configuration interface has a driver bound; refusing to detach it')
            ioctl(self.fd,0x8004550f,ctypes.c_uint(2));self.claimed=True
            return self
        except BaseException:self.close();raise
    def close(self):
        if self.status_fd is not None:os.close(self.status_fd);self.status_fd=None
        if self.fd is not None:
            try:
                if self.claimed:ioctl(self.fd,0x80045510,ctypes.c_uint(2))
            finally:os.close(self.fd);self.fd=None;self.claimed=False
    def __exit__(self,*args):self.close()
    def control(self,rt,rq,value,index,payload):
        n=len(payload) if isinstance(payload,bytes) else payload
        buf=ctypes.create_string_buffer(payload if isinstance(payload,bytes) else payload)
        req=Control(rt,rq,value,index,n,1000,ctypes.cast(buf,ctypes.c_void_p))
        count=ioctl(self.fd,0xc0005500|(ctypes.sizeof(Control)<<16),req)
        if rt&128:return bytes(buf.raw[:count])
        if count!=n:raise RuntimeError(f'Short USB control write: {count}/{n}')
        return count
    def descriptors(self):
        result={}
        for i in (0,1):
            paths=list(Path(self.info['sysfs']).glob(f'*:1.{i}/*/report_descriptor'))
            if len(paths)!=1: raise RuntimeError('Input report descriptor not found in sysfs')
            result[str(i)]=paths[0].read_bytes().hex(' ')
        result['2']=self.control(0x81,6,0x2200,2,28).hex(' ')
        return result
    def send(self,packet):
        if len(packet.header)!=9 or packet.header[0]!=0:raise ValueError('Invalid feature report')
        if len(packet.payload)%64:raise ValueError('Output payload must contain complete 64-byte reports')
        self.control(0x21,9,0x0300,2,packet.header[1:])
        if packet.payload:
            time.sleep(0.010) # Original application's wait helper sleeps approximately 10 ms.
            for i in range(0,len(packet.payload),64):
                chunk=packet.payload[i:i+64];buf=ctypes.create_string_buffer(chunk)
                req=Bulk(3,len(chunk),1000,ctypes.cast(buf,ctypes.c_void_p))
                count=ioctl(self.fd,0xc0005502|(ctypes.sizeof(Bulk)<<16),req)
                if count!=64:raise RuntimeError(f'Short USB output write: {count}/64')
                time.sleep(0.020)
            time.sleep(0.010)
    def status(self,timeout=1.5):
        # Drain stale reports; never retain or print keyboard/consumer-control data.
        drain_deadline=time.monotonic()+0.05
        while time.monotonic()<drain_deadline and select.select([self.status_fd],[],[],0)[0]:
            os.read(self.status_fd,64)
        self.send(sync_packet());deadline=time.monotonic()+timeout
        reports=[]
        while time.monotonic()<deadline:
            if not select.select([self.status_fd],[],[],max(0,deadline-time.monotonic()))[0]:break
            report=os.read(self.status_fd,64)
            if len(report)==7 and report[:2]==b'\x05\x00':
                decoded=decode_status(report);reports.append(decoded)
                if decoded['event']==255:return decoded
        if reports:return reports[-1]
        raise RuntimeError('No vendor status response to sync request; no configuration was written')
