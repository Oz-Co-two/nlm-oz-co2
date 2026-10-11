// editor.html から分離（2026-09-28）: CSP(Content-Security-Policy)でインラインスクリプトを禁止するため外部ファイル化。
// ※ 先頭の合言葉の部分は、他のどの通信よりも前に動く必要がある（ここが最初に読まれるスクリプト）。
// モジュール(main.js)より前に同期で読み込まれる必要がある＝editor.htmlでは type="module" を付けずに読み込むこと。
// 個人の環境設定(bsnm_*)を config/settings.json にミラー保存＝localStorage喪失(サイトデータ削除/別オリジン)対策。
// localStorage は従来どおり作業キャッシュとして使い、起動時にファイル→localStorage、変更時にlocalStorage→ファイル。
// ※UIレイアウト系(パネル位置/画面比率/色履歴)は高頻度・マシン依存のためファイル対象外＝localStorage専用。
// ※フォルダ/音源のFileHandle(IndexedDB)はJSON化不可なので対象外（従来どおりIndexedDB保持）。
// 合言葉（2026-10-11）: serve.py は起動ごとの合言葉を X-NLM-Token ヘッダーで求める（静的ファイルを除く。serve.py の SESSION_TOKEN）。
// 画面へは URL の #k=… で渡る。同じオリジンへの fetch / XHR に自動で付ける＝個々の通信で付け忘れない（このファイルが最初に読まれる）。
(function(){
  var m=/(?:^#|&)k=([A-Za-z0-9_-]+)/.exec(location.hash), tok=m?m[1]:'';
  if(!tok){ if(location.protocol.indexOf('http')===0) window.__nlmNoToken=true; return; }   // 案内は editor-app.js（言語の読込後）
  function same(u){ try{ return new URL(u,location.href).origin===location.origin; }catch(_){ return false; } }
  var _fetch=window.fetch;
  window.fetch=function(input,init){
    var req=(typeof Request!=='undefined'&&input instanceof Request);
    if(same(req?input.url:String(input))){
      init=Object.assign({},init||{});
      var h=new Headers(init.headers||(req?input.headers:undefined));   // init.headers は Request 側のヘッダーを丸ごと置き換えるので合成する
      h.set('X-NLM-Token',tok); init.headers=h;
    }
    return _fetch.call(window,input,init);
  };
  var _open=XMLHttpRequest.prototype.open, _send=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(method,url){ this._nlmTok=same(url); return _open.apply(this,arguments); };
  XMLHttpRequest.prototype.send=function(){ if(this._nlmTok) this.setRequestHeader('X-NLM-Token',tok); return _send.apply(this,arguments); };
})();
(function(){
  // ファイルにミラーしない=localStorage専用（Tauri住み分け: UIレイアウト/高頻度/マシン依存）
  var LOCAL_ONLY={bsnm_keypos:1,bsnm_keyfold:1,bsnm_split:1};
  // ① 起動時: config/settings.json を読み、bsnm_* を localStorage へ流し込む（モジュールがlocalStorageを同期読みする前に確定させる）
  try{
    var xhr=new XMLHttpRequest();
    xhr.open('GET','config/settings.json?v='+Date.now(),false);   // 同期: モジュール実行前に確定が必要
    xhr.send();
    if(xhr.status>=200&&xhr.status<300&&xhr.responseText){
      var o=JSON.parse(xhr.responseText);
      for(var k in o){ if(k.indexOf('bsnm_')===0&&!LOCAL_ONLY[k]){ try{ localStorage.setItem(k,o[k]); }catch(_){} } }
    }
  }catch(_){}
  // ② 変更時: bsnm_* の set/remove を捕捉し、デバウンスで config/settings.json へ書き戻す（LOCAL_ONLYは除外）
  var _set=localStorage.setItem.bind(localStorage), _rm=localStorage.removeItem.bind(localStorage), _t=null;
  function schedule(){ if(_t) clearTimeout(_t); _t=setTimeout(function(){
    var data={}; for(var i=0;i<localStorage.length;i++){ var key=localStorage.key(i); if(key&&key.indexOf('bsnm_')===0&&!LOCAL_ONLY[key]) data[key]=localStorage.getItem(key); }
    try{ fetch('__settings/save',{method:'POST',headers:{'Content-Type':'application/json','X-NLM-Request':'1'},body:JSON.stringify({data:data})}); }catch(_){}
  },400); }
  localStorage.setItem=function(k,v){ _set(k,v); if((''+k).indexOf('bsnm_')===0) schedule(); };
  localStorage.removeItem=function(k){ _rm(k); if((''+k).indexOf('bsnm_')===0) schedule(); };
  // ③ 廃止済みキーの掃除: 誰も読まなくなった旧キーを localStorage / settings.json から除去（ミラーが全bsnm_*を書き戻すため放置すると永続する）。監査 2026-07-14
  ['bsnm_cpal','bsnm_cphist'].forEach(function(k){ try{ if(localStorage.getItem(k)!=null) localStorage.removeItem(k); }catch(_){} });   // bsnm_cpal=クロマパレットはper-project化 / bsnm_cphist=色履歴パレット廃止
})();
