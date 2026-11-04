"""Generated, specified-note test data; no external or client scores."""
import zlib

def u16(n,order):return n.to_bytes(2,order)
def u32(n,order):return n.to_bytes(4,order)

def fixture(order,layout,broken=None):
    def rows(tag,key,payload,key2=None):
        width=12 if key2 is None else 10
        assert len(payload)%width==0
        header=u16(key,order)+(u16(key2,order) if key2 is not None else b'')
        header+=tag.encode() if order=='big' else tag[::-1].encode()
        return b''.join(header+payload[i:i+width] for i in range(0,len(payload),width))
    others=rows('MS',1,b''.join(u16(n,order) for n in [600,0,4,1024,0,16]))
    others+=rows('IS',1,bytes(36))
    data=[]
    for layer in range(1,5):
        frame=1000+layer
        number=layer
        end=5 if layer==1 else number
        if broken=='missing' and layer==1:end=999
        others+=rows('FR',frame,u32(number,order)+u32(end,order)+bytes(4))
        slot=bytearray(38)
        slot[:4]=u32(number,order)
        slot[10:14]=u32(5 if layer==1 else 0,order)
        slot[14:16]=u16(1024,order)
        slot[18:22]=u32(0xC0000000,order)
        slot[24:26]=u16(1,order)
        slot[26:28]=u16((layer-1)<<4,order)
        slot[28:32]=u32(0x80000000,order)
        data.append(bytes(slot))
    rest=bytearray(38)
    rest[:4]=u32(5,order)
    rest[6:10]=u32(1,order)
    rest[14:16]=u16(1024,order)
    rest[18:22]=u32(0x80000000,order)  # Positioned rest with a fake pitch.
    rest[24:26]=u16(1,order)
    rest[26:28]=u16(160,order)
    rest[28:32]=u32(0x80000000,order)
    if broken=='cycle':rest[10:14]=u32(1,order)
    data.append(bytes(rest))
    data.append(u32(9999,order)+bytes(34))  # Deleted database slot.
    gf=bytearray(20)
    base=4 if layout=='etf' else 6
    percent_at=12 if layout=='etf' else 4
    gf[percent_at:percent_at+2]=u16(75,order)
    for layer in range(4):gf[base+2*layer:base+2*layer+2]=u16(1001+layer,order)
    details=rows('GF',1,bytes(gf[:10] if broken=='unverified' else gf),1)
    header=bytearray(512)
    header[:18]=b'ENIGMA BINARY FILE'
    banner=b'Finale(R) 2000 Test'
    header[32:32+len(banner)]=banner
    pools=[others,details,b''.join(data),b'^block(1)Test^end']
    if broken=='truncated':pools[2]=pools[2][:-1]
    return bytes(header)+b''.join(u16(i+1,order)+u32(len(p)+6,order)+p for i,p in enumerate(pools))


def modern_fixture(year=2011,level=6):
    """One known four-layer score in a zlib-record container."""
    raw=fixture('little','extended')
    pools=[];position=512
    for _ in range(4):
        length=int.from_bytes(raw[position+2:position+6],'little')
        pools.append(raw[position+6:position+length]);position+=length
    def other(tag,key,payload):
        return u16(tag,'little')+u16(key,'little')+bytes(2)+u32(len(payload),'little')+payload+bytes(4)
    def detail(tag,staff,measure,payload):
        return u16(tag,'little')+u16(staff,'little')+u16(measure,'little')+bytes(2)+u32(len(payload),'little')+payload+bytes(4)
    # Ordinary unknown option records keep the first pool above the upstream
    # zlib recognizer's minimum, without borrowing a real score's settings.
    others=b''.join(other(tag,65534,bytes(64)) for tag in range(1,91))
    others+=other(176,1,b''.join(u16(n,'little') for n in [600,0,4,1024,0,16]))
    others+=other(231,1,bytes(36))
    others+=other(159,0,u16(1,'little')+bytes(22))
    for layer in range(1,5):
        others+=other(146,1000+layer,u32(layer,'little')+u32(5 if layer==1 else layer,'little')+bytes(4))
    gf=bytearray(20);gf[4:6]=u16(75,'little')
    for i in range(4):gf[6+2*i:8+2*i]=u16(1001+i,'little')
    details=b''.join(detail(2000+i,i+1,0,bytes(8)) for i in range(60))
    details+=detail(1044,1,1,bytes(gf))
    header=bytearray(512);header[:18]=b'ENIGMA BINARY FILE'
    banner=f'Finale(R) {year} Test'.encode();header[32:32+len(banner)]=banner
    output=[]
    for i,data in enumerate([others,details,pools[2],pools[3]]):
        stream=zlib.compress(data,level)
        output.append(u16(15+i,'little')+u32(len(stream)+10,'little')+bytes(4)+stream)
    return bytes(header)+b''.join(output)
