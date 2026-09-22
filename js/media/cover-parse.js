// 埋め込みアートワーク抽出（純バイト解析・依存ゼロ）。editor-app.js から切り出し（監査 2026-07-14）
// MP3=ID3v2 APIC / FLAC=PICTURE / OGG・EGG=Vorbis METADATA_BLOCK_PICTURE / MP4=covr
export function _sniffMime(d){
  if(d[0]===0x89&&d[1]===0x50) return 'image/png';
  if(d[0]===0xFF&&d[1]===0xD8) return 'image/jpeg';
  if(d[0]===0x47&&d[1]===0x49&&d[2]===0x46) return 'image/gif';
  if(d[0]===0x42&&d[1]===0x4D) return 'image/bmp';
  return 'image/jpeg';
}
export function _rd32be(u,p){ return (u[p]<<24|u[p+1]<<16|u[p+2]<<8|u[p+3])>>>0; }
// FLAC PICTURE ブロック本体（picType(4)+MIME長+MIME+desc長+desc+w/h/depth/colors(16)+data長+data）
export function _parseFlacPic(u,s,e){
  let p=s;
  p+=4;                                   // picture type
  const mlen=_rd32be(u,p); p+=4; let mime=''; for(let i=0;i<mlen;i++) mime+=String.fromCharCode(u[p+i]); p+=mlen;
  const dlen=_rd32be(u,p); p+=4; p+=dlen; // description
  p+=16;                                  // width,height,depth,colors
  const plen=_rd32be(u,p); p+=4;
  const data=u.subarray(p,Math.min(e,p+plen));
  if(!data.length) return null;
  return {mime:mime||_sniffMime(data), data};
}
export function _id3Pic(u){
  const ver=u[3];
  const size=(u[6]<<21)|(u[7]<<14)|(u[8]<<7)|u[9];   // synchsafe
  let p=10; const end=Math.min(u.length,10+size);
  const parseAPIC=(s,e,v22)=>{
    let p=s; const enc=u[p]; p++; let mime='';
    if(v22){ mime=/png/i.test(String.fromCharCode(u[p],u[p+1],u[p+2]))?'image/png':'image/jpeg'; p+=3; }
    else { while(p<e&&u[p]!==0){ mime+=String.fromCharCode(u[p]); p++; } p++; }
    p++;                                              // picture type
    if(enc===1||enc===2){ while(p+1<e&&!(u[p]===0&&u[p+1]===0)) p+=2; p+=2; }
    else { while(p<e&&u[p]!==0) p++; p++; }
    const data=u.subarray(p,e);
    if(!data.length) return null;
    return {mime:mime||_sniffMime(data), data};
  };
  while(p+10<=end){
    if(ver===2){                                      // ID3v2.2: 3文字ID+3バイトサイズ
      const id=String.fromCharCode(u[p],u[p+1],u[p+2]);
      if(u[p]===0) break;
      const fsize=(u[p+3]<<16)|(u[p+4]<<8)|u[p+5], fdata=p+6;
      if(id==='PIC') return parseAPIC(fdata,fdata+fsize,true);
      if(fsize<=0) break; p=fdata+fsize;
    } else {
      const id=String.fromCharCode(u[p],u[p+1],u[p+2],u[p+3]);
      if(u[p]===0) break;
      const fsize=(ver===4?((u[p+4]<<21)|(u[p+5]<<14)|(u[p+6]<<7)|u[p+7]):_rd32be(u,p+4))>>>0, fdata=p+10;
      if(id==='APIC') return parseAPIC(fdata,fdata+fsize,false);
      if(fsize<=0) break; p=fdata+fsize;
    }
  }
  return null;
}
export function _flacPic(u){   // u は "fLaC" の後ろから
  let p=0;
  while(p+4<=u.length){
    const flag=u[p], last=flag&0x80, type=flag&0x7f;
    const len=(u[p+1]<<16)|(u[p+2]<<8)|u[p+3], body=p+4;
    if(type===6) return _parseFlacPic(u,body,body+len);
    if(last) break; p=body+len;
  }
  return null;
}
export function _oggPic(u){    // OggS ページを再構成し、コメントパケットの METADATA_BLOCK_PICTURE を取り出す
  let p=0; const packets=[]; let cur=[];
  while(p+27<=u.length){
    if(!(u[p]===0x4F&&u[p+1]===0x67&&u[p+2]===0x67&&u[p+3]===0x53)) break;
    const nseg=u[p+26], segTable=p+27;
    if(segTable+nseg>u.length) break;
    let sp=segTable+nseg;
    for(let i=0;i<nseg;i++){
      const lace=u[segTable+i];
      for(let b=0;b<lace&&sp+b<u.length;b++) cur.push(u[sp+b]);
      sp+=lace;
      if(lace<255){ packets.push(cur); cur=[]; }
    }
    p=sp;
    if(packets.length>=2) break;
  }
  if(packets.length<2) return null;
  const cu=Uint8Array.from(packets[1]);
  let q=7;                                             // 0x03"vorbis"
  const isVorbis=cu[0]===0x03&&cu[1]===0x76&&cu[2]===0x6F&&cu[3]===0x72&&cu[4]===0x62&&cu[5]===0x69&&cu[6]===0x73;
  const isOpus=String.fromCharCode(...cu.subarray(0,8))==='OpusTags';
  if(isOpus) q=8; else if(!isVorbis) q=7;
  const rd=()=>{ const v=(cu[q]|cu[q+1]<<8|cu[q+2]<<16|cu[q+3]<<24)>>>0; q+=4; return v; };
  const vlen=rd(); q+=vlen;                            // vendor
  const n=rd();
  for(let i=0;i<n&&q<cu.length;i++){
    const clen=rd(); let j=q, key='';
    while(j<q+clen&&cu[j]!==0x3D){ key+=String.fromCharCode(cu[j]); j++; }
    if(key.toUpperCase()==='METADATA_BLOCK_PICTURE'){
      try{
        let b64=''; for(let k=j+1;k<q+clen;k++) b64+=String.fromCharCode(cu[k]);
        const bin=atob(b64.replace(/\s/g,'')); const pb=new Uint8Array(bin.length);
        for(let k=0;k<bin.length;k++) pb[k]=bin.charCodeAt(k);
        return _parseFlacPic(pb,0,pb.length);
      }catch(e){ return null; }
    }
    q+=clen;
  }
  return null;
}
export function _mp4FindAtom(u,start,end,path){
  let p=start;
  while(p+8<=end){
    let size=_rd32be(u,p); const type=String.fromCharCode(u[p+4],u[p+5],u[p+6],u[p+7]); let hdr=8;
    if(size===1){ size=(u[p+8]*4294967296)+_rd32be(u,p+12); hdr=16; }
    else if(size===0){ size=end-p; }
    if(size<8) break;
    const cs=p+hdr, ce=Math.min(end,p+size);
    if(type===path[0]){
      if(path.length===1) return {start:cs,end:ce};
      const r=_mp4FindAtom(u,type==='meta'?cs+4:cs,ce,path.slice(1));
      if(r) return r;
    }
    p+=size;
  }
  return null;
}
export function _mp4Pic(u){
  const covr=_mp4FindAtom(u,0,u.length,['moov','udta','meta','ilst','covr']);
  if(!covr) return null;
  const data=_mp4FindAtom(u,covr.start,covr.end,['data']);
  if(!data) return null;
  const bytes=u.subarray(data.start+8,data.end);     // data アトム: type(4)+locale(4) の後が画像
  if(!bytes.length) return null;
  return {mime:_sniffMime(bytes),data:bytes};
}
