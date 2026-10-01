// editor.html から分離（2026-09-28）: CSP(Content-Security-Policy)でインラインスクリプトを禁止するため外部ファイル化。
// モジュール(main.js)より前に同期で読み込まれる必要がある＝editor.htmlでは type="module" を付けずに読み込むこと。
// 個人の環境設定(bsnm_*)を config/settings.json にミラー保存＝localStorage喪失(サイトデータ削除/別オリジン)対策。
// localStorage は従来どおり作業キャッシュとして使い、起動時にファイル→localStorage、変更時にlocalStorage→ファイル。
// ※UIレイアウト系(パネル位置/画面比率/色履歴)は高頻度・マシン依存のためファイル対象外＝localStorage専用。
// ※フォルダ/音源のFileHandle(IndexedDB)はJSON化不可なので対象外（従来どおりIndexedDB保持）。
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
