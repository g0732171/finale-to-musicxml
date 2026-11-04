'use strict';
const $=id=>document.getElementById(id),token=new URLSearchParams(location.search).get('token');
let selection=null,job=null,busy=false,ready=false,timer=null,viewerScript=null,previewVersion=0;
const labels={pending:'待機中',running:'変換中…',success:'保存済み · 要照合',failed:'失敗',unsupported:'未対応'};
const reasons={changed:'確認後に原本が変更されました。もう一度選択してください。',mus_variant:'このMUSの世代・構造は現在読み取れません。FinaleでMUSXとして保存するか、MusicXMLへ書き出してください。',conversion_error:'このファイルの形式・内容を読み取れませんでした。',timeout:'処理時間の上限に達しました。',too_large:'1ファイル20 MBまでです。',save_error:'保存先への書き込みに失敗しました。'};
function url(path){return path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(token);}
function make(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function tell(text){$('message').textContent=text;$('message').hidden=!text;}
function setBusy(value){busy=value;for(const id of ['filebutton','folderbutton','clearbutton','resetbutton','quitbutton'])$(id).disabled=value;$('convertbutton').disabled=value||!ready||!selection;}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'X-Finale-Token':token,...options.headers}});let data;try{data=await response.json();}catch{throw new Error('ローカルアプリとの接続が切れました。起動用ファイルから開き直してください。');}if(!response.ok)throw new Error(data.detail||'操作できませんでした。');return data;}
function post(path,data={}){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
function clearResults(){clearTimeout(timer);job=null;$('job-state').hidden=true;$('empty-state').hidden=false;$('resetbutton').hidden=true;$('jobbadge').textContent='変換待ち';}
function showSelection(){
  $('folder-info').hidden=!selection;$('selection').hidden=!selection;if(!selection)return;
  $('source-name').textContent=`${selection.kind==='folder'?'フォルダ':'ファイル'}を選択しました`;$('source-path').textContent=selection.source;
  $('destination-hint').textContent=`保存予定：${selection.output_example}（同名があれば連番を追加）`;
  $('selection-count').textContent=`${selection.count}件 ／ その他${selection.ignored}件・リンク${selection.linked}件を除外${selection.unreadable?` ／ 読み取り不可${selection.unreadable}件`:''}`;
  $('selection-list').replaceChildren();for(const file of selection.files.slice(0,100))$('selection-list').append(make('li','',file));if(selection.count>100)$('selection-list').append(make('li','',`ほか${selection.count-100}件。全件を処理します。`));
}
async function pick(kind){
  if(busy)return;setBusy(true);tell('');$('selection-status').textContent='システムの選択ウィンドウで選んでください…';
  try{const result=await post('/api/choose',{kind});if(result.cancelled){$('selection-status').textContent=selection?'選択をキャンセルしました。前の選択内容を保持しています。':'選択をキャンセルしました。もう一度選んでください。';return;}selection=result;clearResults();showSelection();$('selection-status').textContent=`${selection.count}件の楽譜を確認しました。「MusicXMLに変換する」で変換・保存します。`;}
  catch(error){$('selection-status').textContent=error.message;tell(error.message);}finally{setBusy(false);}
}
async function start(){if(busy||!selection)return;setBusy(true);tell('');try{job=await post('/api/jobs',{selection_id:selection.id});render();poll();}catch(error){tell(error.message);setBusy(false);}}
function render(){
  const done=job.status==='completed',issues=job.counts.failed+job.counts.unsupported;
  $('empty-state').hidden=true;$('job-state').hidden=false;$('resetbutton').hidden=!done;$('jobbadge').textContent=done?(issues?'完了（一部要確認）':'保存完了'):'変換・保存中';
  $('total-stat').textContent=job.files.length;$('success-stat').textContent=job.counts.success;$('issue-stat').textContent=issues;
  const percent=Math.round((job.counts.success+issues)/job.files.length*100);$('progressbar').style.width=percent+'%';document.querySelector('.progress').setAttribute('aria-valuenow',percent);
  $('selection-status').textContent=done?`保存済み${job.counts.success}件、失敗・未対応${issues}件。保存先フォルダを確認してください。`:`${job.counts.success+issues} / ${job.files.length}件を処理しています…`;
  $('file-results').replaceChildren();for(const row of job.files){const entry=make('div','result-row');entry.append(make('span','file-symbol','♪'));const info=make('div');info.append(make('div','result-name',row.name));info.append(make('span','result-status '+row.status,labels[row.status]));const detail=reasons[row.reason]||(row.status==='success'?`${row.parts}パート · ${row.measures}小節（第1パート） · ${row.output}`:'');if(detail)info.append(make('div','result-meta',detail));entry.append(info);const actions=make('div','file-actions');if(row.status==='success'){const button=make('button','','見る');button.setAttribute('aria-label',row.name+' をプレビュー');button.onclick=()=>preview(row);actions.append(button);const link=make('a','','MXL ↓');link.href=url(`/api/jobs/${job.id}/files/${row.index}`);link.setAttribute('aria-label',row.name+' のMXLを保存');actions.append(link);}entry.append(actions);$('file-results').append(entry);}
  $('saved-location').hidden=!done;$('actual-output').textContent=job.output;
  $('archive').hidden=!done||!job.counts.success;$('archive-note').hidden=$('archive').hidden;$('archive').href=url(`/api/jobs/${job.id}/archive`);setBusy(!done);
}
async function poll(){clearTimeout(timer);if(!job)return;try{job=await api('/api/jobs/'+job.id);render();if(job.status!=='completed')timer=setTimeout(poll,600);}catch(error){tell(error.message);setBusy(false);}}
function loadViewer(){if(!viewerScript)viewerScript=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/assets/opensheetmusicdisplay.min.js';script.onload=resolve;script.onerror=()=>{script.remove();viewerScript=null;reject(new Error('viewer'));};document.head.append(script);});return viewerScript;}
function closePreview(){previewVersion++;const dialog=$('previewdialog');if(typeof dialog.close==='function')dialog.close();else dialog.removeAttribute('open');}
async function preview(row){const version=++previewVersion,id=job.id,dialog=$('previewdialog');$('previewtitle').textContent=row.name;$('previewstatus').textContent='楽譜を読み込んでいます…';$('scoreview').replaceChildren();if(typeof dialog.showModal==='function')dialog.showModal();else{dialog.classList.add('preview-fallback');dialog.setAttribute('open','');}try{await loadViewer();const response=await fetch(url(`/api/jobs/${id}/files/${row.index}?xml=true`));if(!response.ok)throw new Error('load');const xml=await response.text();if(version!==previewVersion)return;const score=new opensheetmusicdisplay.OpenSheetMusicDisplay($('scoreview'),{autoResize:true,backend:'svg',drawTitle:true});await score.load(xml);if(version!==previewVersion)return;score.render();$('previewstatus').textContent='このパソコン上で描画しています。原譜と照合してください。';}catch(error){if(version===previewVersion)$('previewstatus').textContent='プレビューできません。保存済みMXLを楽譜ソフトで確認してください。';}}
function reset(){if(busy)return;selection=null;clearResults();showSelection();$('selection-status').textContent='ファイルを1つ、またはフォルダを選んでください。';tell('');setBusy(false);}
$('filebutton').onclick=()=>pick('file');$('folderbutton').onclick=()=>pick('folder');$('convertbutton').onclick=start;$('clearbutton').onclick=reset;$('resetbutton').onclick=reset;
$('openoutput').onclick=async()=>{try{await post(`/api/jobs/${job.id}/open`);}catch(error){tell(error.message);}};
$('closepreview').onclick=closePreview;$('previewdialog').addEventListener('cancel',()=>previewVersion++);
$('quitbutton').onclick=async()=>{if(busy)return;try{await post('/api/quit');ready=false;setBusy(true);tell('ローカルアプリを終了しました。このタブを閉じてください。保存したMXLは残っています。');}catch(error){tell(error.message);}};
async function initialize(){try{const health=await api('/api/health');ready=health.ok&&health.offline;selection=health.selection;showSelection();if(health.current_job){job={id:health.current_job};poll();}else setBusy(false);}catch(error){tell(error.message);setBusy(false);}}
document.querySelector('.brand').href=url('/');
initialize();
