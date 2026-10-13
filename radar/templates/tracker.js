(function(){
  var STATUSES=[["applied","Applied"],["interviewing","Interviewing"],["offer","Offer"],["rejected","Rejected"]];
  var ORDER={applied:0,interviewing:1,offer:2,rejected:3};
  var sec=document.getElementById("applied-ledger"),
      rowsEl=document.getElementById("applied-rows"),
      introEl=document.getElementById("applied-intro");
  var dbp=null, rows={};

  function esc(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c];});}
  function today(){var d=new Date(),p=function(n){return (n<10?"0":"")+n;};
    return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}

  function render(){
    var ids=Object.keys(rows);
    Array.prototype.forEach.call(document.querySelectorAll("[data-role-id]"),function(n){
      n.hidden=!!rows[n.getAttribute("data-role-id")];
    });
    if(!ids.length){sec.hidden=true;rowsEl.innerHTML="";introEl.innerHTML="";return;}
    sec.hidden=false;
    ids.sort(function(a,b){
      var d=(ORDER[rows[a].status]||0)-(ORDER[rows[b].status]||0);
      return d||String(rows[b].appliedOn||"").localeCompare(String(rows[a].appliedOn||""));});
    var c={};ids.forEach(function(i){var k=rows[i].status||"applied";c[k]=(c[k]||0)+1;});
    introEl.innerHTML="<b>"+ids.length+"</b> role"+(ids.length===1?"":"s")+" tracked &mdash; "+
      STATUSES.filter(function(x){return c[x[0]];}).map(function(x){
        return "<b>"+c[x[0]]+"</b> "+x[1].toLowerCase();}).join(", ")+".";
    rowsEl.innerHTML=ids.map(function(id){
      var r=rows[id],st=r.status||"applied";
      var when=(r.appliedOn?"applied "+esc(r.appliedOn):"");
      if(r.updatedOn&&r.updatedOn!==r.appliedOn) when+=(when?" &middot; ":"")+"updated "+esc(r.updatedOn);
      return '<div class="led">'+
        '<div class="role-top"><div>'+
        '<div class="co">'+(r.url?'<a href="'+esc(r.url)+'">'+esc(r.company)+"</a>":esc(r.company))+"</div>"+
        '<div class="title">'+esc(r.title)+"</div>"+
        '<div class="loc">'+when+"</div></div></div>"+
        '<div class="chips"><span class="chip '+esc(st)+'">'+esc(st)+"</span></div>"+
        (r.note?'<p class="note">'+esc(r.note)+"</p>":"")+
        '<div class="track">'+STATUSES.filter(function(x){return x[0]!==st;}).map(function(x){
          return '<button class="tbtn sec" data-set="'+x[0]+'" data-id="'+esc(id)+'">'+x[1]+"</button>";}).join("")+
        '<button class="tbtn sec" data-clear="'+esc(id)+'">Untrack</button></div></div>';
    }).join("");
  }

  function put(id,data){ if(dbp) dbp.then(function(db){ if(db) db.doc("applications/"+id).set(data).catch(function(){}); }); }
  function drop(id){ if(dbp) dbp.then(function(db){ if(db) db.doc("applications/"+id).delete().catch(function(){}); }); }

  document.addEventListener("click",function(e){
    var t=e.target; if(!t||!t.closest) return;
    var b=t.closest("button"); if(!b) return;
    if(b.hasAttribute("data-act")){
      var card=b.closest("[data-role-id]"); if(!card) return;
      var d=today();
      put(card.getAttribute("data-role-id"),{status:"applied",
        company:card.getAttribute("data-company")||"",title:card.getAttribute("data-title")||"",
        url:card.getAttribute("data-url")||"",appliedOn:d,updatedOn:d,note:""});
    } else if(b.hasAttribute("data-set")){
      var id=b.getAttribute("data-id"),cur=rows[id]||{},next={};
      for(var k in cur) next[k]=cur[k];
      next.status=b.getAttribute("data-set"); next.updatedOn=today();
      if(!next.appliedOn) next.appliedOn=today();
      put(id,next);
    } else if(b.hasAttribute("data-clear")){ drop(b.getAttribute("data-clear")); }
  });

  dbp=(window.claude&&window.claude.use)?window.claude.use("db"):null;
  if(!dbp) return;
  dbp.then(function(db){
    if(!db) return;
    document.documentElement.setAttribute("data-track-live","1");
    db.collection("applications").onSnapshot(function(snap){
      rows={}; snap.docs.forEach(function(d){ if(d.exists) rows[d.id]=d.data()||{}; });
      render();
    },function(){});
  });
})();
