/* Apply bridge for the existing Mountain preview. All writes stay localhost. */
(async function () {
  const toolbar = document.querySelector('.toolbar');
  const panel = document.createElement('section');
  panel.style.cssText = 'padding:12px 24px;background:#20262e;border-bottom:1px solid #31e5ee;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
  const applyButton = document.createElement('button'); applyButton.textContent = 'Apply to game';
  const reload = document.createElement('button'); reload.textContent = 'Load installed settings';
  const globalLabel = document.createElement('label'); globalLabel.textContent = 'Starting global depth ';
  const global = document.createElement('input'); global.type = 'number'; global.min = 0; global.max = 1; global.step = .1; global.setAttribute('aria-label','Starting global depth');
  globalLabel.append(global);
  const liveLabel = document.createElement('label'), live = document.createElement('input'); live.type = 'checkbox'; liveLabel.append(live,' Enable +/− in game');
  const progress = document.createElement('span'); progress.setAttribute('role','status'); progress.setAttribute('aria-live','polite'); progress.textContent = 'Loading installed settings…';
  panel.append(applyButton,reload,globalLabel,liveLabel,progress); toolbar.after(panel);
  applyButton.disabled = reload.disabled = true;
  document.querySelector('header h1').textContent = 'Mountain relief settings';
  const paragraphs = document.querySelectorAll('header p');
  paragraphs[0].textContent = 'Tune one head per texture family. Drag to rotate, scroll over the surface to zoom, and compare relief ON / OFF. Apply to game saves the YAML, rebuilds changed maps and installs them with a backup.';
  paragraphs[1].textContent = 'The page starts with your installed values. Preview ON / OFF is a comparison switch; use the variant checkboxes to exclude specific textures from the game shader.';
  paragraphs[2].textContent = 'Preview lighting approximates the game. Close the game before Apply. Starting global depth and +/− controls take effect next launch; rebuilding family depths and exclusions is automatic.';
  let current, busy = false, checks = [];
  const status = text => { progress.textContent = text; $('saveStatus').textContent = text; };
  const getJSON = async (url,options) => {const response = await fetch(url,options),data = await response.json();if(!response.ok)throw Error(data.error||'Request failed');return data;};
  function locked(value) {
    busy = value; applyButton.disabled = reload.disabled = global.disabled = live.disabled = value;
    for (const card of cards) {
      card.node.querySelectorAll('.controls input,.controls button').forEach(el => el.disabled=value||!card.item.enabled||!(card.item.id in (current?.families||{})));
    }
    checks.forEach(x=>x.input.disabled=value);
  }
  function setGain(card,gain) {
    state[card.item.id].gain=gain;
    const control=card.node.querySelector('.controls');
    control.querySelector('input[type=range]').value=gain;
    control.querySelector('input[type=number]').value=gain;
    control.querySelector('strong').textContent=formatGain(gain)+'×';
    request(card);
  }
  function exclusions() {
    checks.forEach(x=>x.container.remove());checks=[];
    for(const card of cards) {
      if(!(card.item.id in current.families))continue;
      const container=document.createElement('details'),summary=document.createElement('summary');
      summary.textContent='Variants excluded from the game shader';container.append(summary);
      const seen=new Set();
      for(const member of card.item.members) {
        const name=member.replace(/\.png$/,'').replace(/_dk$/,'');
        if(!current.allowed_variants.includes(name)||seen.has(name))continue;
        seen.add(name);
        const label=document.createElement('label'),input=document.createElement('input');
        label.style.cssText='display:block;margin:8px 0;overflow-wrap:anywhere';input.type='checkbox';input.checked=current.excluded_variants.includes(name);
        label.append(input,' '+member);container.append(label);checks.push({name,input,container});
        input.onchange=()=>status('Unapplied changes. Click Apply to game when ready.');
      }
      card.node.querySelector('.footer').prepend(container);
    }
  }
  async function loadInstalled() {
    locked(true);
    try {
      current=await getJSON('/api/config');
      global.value=current.global_depth_initial;live.checked=current.live_tuner;
      for(const card of cards) {
        if(card.item.id in current.families) {
          setGain(card,current.families[card.item.id]);
          const tag=card.node.querySelector('.tag');tag.textContent='Installed settings';tag.classList.remove('candidate');
          const desc=card.node.querySelector('.footer p');desc.textContent=desc.textContent.replaceAll('Not installed.','').replaceAll('not installed','preview');
        }
      }
      exclusions();save();status(`Installed: ${Object.keys(current.families).length} families · ${current.audit.excluded_materials} materials excluded.`);
    } finally {locked(false);}
  }
  reload.onclick=()=>loadInstalled().catch(e=>status(e.message));
  panel.addEventListener('input',()=>{if(!busy)status('Unapplied changes. Click Apply to game when ready.');});
  document.querySelector('main').addEventListener('input',e=>{if(!busy&&e.target.closest('.controls'))status('Unapplied changes. Click Apply to game when ready.');});
  applyButton.onclick=async()=>{
    if(busy||!current)return;
    const gains=Object.fromEntries(Object.keys(current.families).map(id=>[id,state[id].gain]));
    const payload={revision:current.revision,families:gains,excluded_variants:[...new Set(checks.filter(x=>x.input.checked).map(x=>x.name))],global_depth_initial:Number(global.value),live_tuner:live.checked};
    locked(true);status('Preparing your changes…');
    try {
      await getJSON('/api/apply',{method:'POST',headers:{'Content-Type':'application/json','X-Relief-Token':current.token},body:JSON.stringify(payload)});
      while(true) {
        await new Promise(resolve=>setTimeout(resolve,1200));
        const job=await getJSON('/api/status');status(job.message);
        if(job.state==='failed')throw Error(job.message);
        if(job.state==='complete') {
          current=await getJSON('/api/config');
          status('Applied to game. Backup saved. Ready for your next launch.');
          break;
        }
      }
    } catch(error) {status('Not applied: '+error.message);}
    finally {locked(false);}
  };
  // Carry notes/camera from the old file page without sending them to the server.
  if(location.hash.startsWith('#review=')) {
    try {
      const old=JSON.parse(decodeURIComponent(location.hash.slice(8)));
      for(const [id,s] of Object.entries(old)) if(state[id]) {
        if(typeof s.note==='string')state[id].note=s.note;
        for(const k of ['yaw','pitch','zoom'])if(Number.isFinite(s[k]))state[id][k]=s[k];
      }
      cards.forEach(card=>{card.node.querySelector('textarea').value=state[card.item.id].note;});
      history.replaceState(null,'',location.pathname);save();
    }catch(e){status('Could not transfer old notes. The original file page still retains them.');}
  }
  try {await loadInstalled();} catch(error) {status('Cannot load installed settings: '+error.message);applyButton.disabled=true;}
})();
