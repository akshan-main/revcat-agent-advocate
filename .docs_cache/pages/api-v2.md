<!doctype html>
<html lang="en" dir="ltr" data-has-hydrated="false">
<head>
<meta charset="UTF-8">
<meta name="generator" content="Docusaurus v3.9.2">
<title data-rh="true">In-App Subscriptions Made Easy â RevenueCat</title><meta data-rh="true" property="og:title" content="In-App Subscriptions Made Easy â RevenueCat"><meta data-rh="true" name="viewport" content="width=device-width,initial-scale=1"><meta data-rh="true" name="twitter:card" content="summary_large_image"><meta data-rh="true" property="og:image" content="https://www.revenuecat.com/docs/img/social-preview.jpg"><meta data-rh="true" name="twitter:image" content="https://www.revenuecat.com/docs/img/social-preview.jpg"><meta data-rh="true" property="og:url" content="https://www.revenuecat.com/docs/api-v2"><meta data-rh="true" property="og:locale" content="en"><meta data-rh="true" name="docusaurus_locale" content="en"><meta data-rh="true" name="docusaurus_tag" content="default"><meta data-rh="true" name="docsearch:language" content="en"><meta data-rh="true" name="docsearch:docusaurus_tag" content="default"><meta data-rh="true" name="google-site-verification" content="SET_BY_CI"><link data-rh="true" rel="icon" href="/docs/img/favicon-32x32.png"><link data-rh="true" rel="canonical" href="https://www.revenuecat.com/docs/api-v2"><link data-rh="true" rel="alternate" href="https://www.revenuecat.com/docs/api-v2" hreflang="en"><link data-rh="true" rel="alternate" href="https://www.revenuecat.com/docs/api-v2" hreflang="x-default"><link rel="preconnect" href="https://www.googletagmanager.com">
<script>window.dataLayer=window.dataLayer||[]</script>
<script>!function(e,t,a,n){e[n]=e[n]||[],e[n].push({"gtm.start":(new Date).getTime(),event:"gtm.js"});var g=t.getElementsByTagName(a)[0],m=t.createElement(a);m.async=!0,m.src="https://www.googletagmanager.com/gtm.js?id=GTM-NJWQK6DX",g.parentNode.insertBefore(m,g)}(window,document,"script","dataLayer")</script>







<link rel="search" type="application/opensearchdescription+xml" title="In-App Subscriptions Made Easy â RevenueCat" href="/docs/opensearch.xml">



<script>window._6si=window._6si||[],window._6si.push(["enableEventTracking",!0]),window._6si.push(["setToken","34fc55a78fae7d6773b87464403be12b"]),window._6si.push(["setEndpoint","b.6sc.co"]),function(){var e=document.createElement("script");e.type="text/javascript",e.async=!0,e.src="//j.6sc.co/6si.min.js";var n=document.getElementsByTagName("script")[0];n.parentNode.insertBefore(e,n)}()</script>
<script>!function(){var e="analytics",t=window[e]=window[e]||[];if(!t.initialize)if(t.invoked)window.console&&console.error&&console.error("Segment snippet included twice.");else{t.invoked=!0,t.methods=["trackSubmit","trackClick","trackLink","trackForm","pageview","identify","reset","group","track","ready","alias","debug","page","screen","once","off","on","addSourceMiddleware","addIntegrationMiddleware","setAnonymousId","addDestinationMiddleware","register"],t.factory=function(n){return function(){if(window[e].initialized)return window[e][n].apply(window[e],arguments);var i=Array.prototype.slice.call(arguments);if(["track","screen","alias","group","page","identify"].indexOf(n)>-1){var r=document.querySelector("link[rel='canonical']");i.push({__t:"bpc",c:r&&r.getAttribute("href")||void 0,p:location.pathname,u:location.href,s:location.search,t:document.title,r:document.referrer})}return i.unshift(n),t.push(i),t}};for(var n=0;n<t.methods.length;n++){var i=t.methods[n];t[i]=t.factory(i)}t.load=function(n,i){var r=document.createElement("script");r.type="text/javascript",r.async=!0,r.setAttribute("data-global-segment-analytics-key",e),r.src="https://cdn.segment.com/analytics.js/v1/"+n+"/analytics.min.js";var a=document.getElementsByTagName("script")[0];a.parentNode.insertBefore(r,a),t._loadOptions=i},t._writeKey="Z9Qk96wxF3Ly91InxqD3kfHCuUG5HGz1",t.SNIPPET_VERSION="5.2.1",t.load("Z9Qk96wxF3Ly91InxqD3kfHCuUG5HGz1")}}()</script>
<script>var hsscript=document.createElement("script");hsscript.src="https://cdn.jsdelivr.net/npm/hockeystack@latest/hockeystack.min.js",hsscript.async=1,hsscript.dataset.apikey="e7f29c7f8f2dc070710f2b8048e147",hsscript.dataset.cookieless=1,hsscript.dataset.autoIdentify=1,document.getElementsByTagName("head")[0].append(hsscript)</script>
<link rel="preconnect" href="https://www.google-analytics.com">
<link rel="preconnect" href="https://www.googletagmanager.com">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-0MLNVKXFGB"></script>
<script>function gtag(){dataLayer.push(arguments)}window.dataLayer=window.dataLayer||[],gtag("js",new Date),gtag("config","G-0MLNVKXFGB",{anonymize_ip:!0})</script><link rel="stylesheet" href="/docs/assets/css/styles.f7f0551f.css">
<script src="/docs/assets/js/runtime~main.5dc8bd88.js" defer="defer"></script>
<script src="/docs/assets/js/main.4e2c160d.js" defer="defer"></script>
</head>
<body class="navigation-with-keyboard">
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-NJWQK6DX" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>






<svg style="display: none;"><defs>
<symbol id="theme-svg-external-link" viewBox="0 0 24 24"><path fill="currentColor" d="M21 13v10h-21v-19h12v2h-10v15h17v-8h2zm3-12h-10.988l4.035 4-6.977 7.07 2.828 2.828 6.977-7.07 4.125 4.172v-11z"/></symbol>
</defs></svg>
<script>!function(){var t=function(){try{return new URLSearchParams(window.location.search).get("docusaurus-theme")}catch(t){}}()||function(){try{return window.localStorage.getItem("theme")}catch(t){}}();document.documentElement.setAttribute("data-theme",t||(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light")),document.documentElement.setAttribute("data-theme-choice",t||"system")}(),function(){try{const c=new URLSearchParams(window.location.search).entries();for(var[t,e]of c)if(t.startsWith("docusaurus-data-")){var a=t.replace("docusaurus-data-","data-");document.documentElement.setAttribute(a,e)}}catch(t){}}()</script><div id="__docusaurus"></div>
</body>
</html>