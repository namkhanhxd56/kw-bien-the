// Chạy trong mọi trang/khung *.helium10.com (world MAIN), trước script của trang.
// Ghi lại request fetch/XHR và dữ liệu trang nhận về, để biết Cerebro chạy thế nào. Chỉ chuyển cho
// capture-relay.js; relay quyết định có gửi về tool hay không (khi bật "Soi Cerebro" trong popup).
(() => {
  if (window.__kwbtCapture) return;
  window.__kwbtCapture = true;

  const BO_QUA = /\.(js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|map)(\?|$)/i;
  const MAX_REQ = 20000, MAX_RES = 60000;
  const AN_HEADER = /authorization|cookie|token|csrf|xsrf|secret|session/i;

  const anBody = s => String(s).replace(/((?:_?csrf|xsrf|authenticity)[\w-]*["']?\s*[=:]\s*["']?)[^&"',\s}]+/gi, "$1[ẩn]");
  const cat = (s, n) => (s == null ? null : (s.length > n ? s.slice(0, n) + `…[cắt, dài ${s.length}]` : s));
  const tuyetDoi = u => { try { return new URL(u, location.href).href; } catch { return String(u); } };
  // Dữ liệu Cerebro có thể đi qua tên miền khác (Pacvue là công ty mẹ của H10), nên ghi mọi request
  // của trang trừ quảng cáo/thống kê.
  const RAC = /google-analytics|googletagmanager|google\.com\/(ccm|rmkt|pagead)|analytics\.google|doubleclick|getbeamer|sentry|hotjar|intercom|segment\.(io|com)|cdn-cgi\/rum|clarity\.ms|facebook|tiktok/i;
  const canGhi = u => /^https?:/i.test(u) && !BO_QUA.test(u) && !RAC.test(u);

  function bodyText(b) {
    if (b == null) return null;
    if (typeof b === "string") return b;
    if (b instanceof URLSearchParams) return b.toString();
    if (b instanceof FormData) return [...b.entries()].map(([k, v]) => `${k}=${typeof v === "string" ? v : "[file]"}`).join("&");
    return `[${Object.prototype.toString.call(b)}]`;
  }
  function headerNames(h) {
    const out = {};
    try { new Headers(h || {}).forEach((v, k) => { out[k] = AN_HEADER.test(k) ? "[ẩn]" : v; }); } catch { /* bỏ qua */ }
    return out;
  }
  function gui(item) {
    item.page = location.pathname + location.search;
    item.t = Date.now();
    window.postMessage({ __kwbt: "capture", item }, location.origin);
  }

  const goc = window.fetch;
  window.fetch = async function (input, init) {
    const url = tuyetDoi(typeof input === "string" || input instanceof URL ? input : input.url);
    const method = (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    const res = await goc.apply(this, arguments);
    if (canGhi(url)) {
      const item = { kind: "fetch", method, url, req_headers: headerNames(init?.headers || (input instanceof Request ? input.headers : null)),
        req_body: cat(anBody(bodyText(init?.body) ?? ""), MAX_REQ), status: res.status, res_type: res.headers.get("content-type") || "" };
      res.clone().text().then(t => gui({ ...item, res_body: /json|text|html|csv/.test(item.res_type) ? cat(t, MAX_RES) : `[${item.res_type}, ${t.length} byte]` }))
        .catch(() => gui(item));
    }
    return res;
  };

  const XO = XMLHttpRequest.prototype.open, XS = XMLHttpRequest.prototype.send, XH = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__kwbt = { method: String(method).toUpperCase(), url: tuyetDoi(url), headers: {} };
    return XO.apply(this, arguments);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    if (this.__kwbt) this.__kwbt.headers[k] = AN_HEADER.test(k) ? "[ẩn]" : v;
    return XH.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    const m = this.__kwbt;
    if (m && canGhi(m.url)) {
      this.addEventListener("loadend", () => {
        let t;
        try { t = this.responseType === "" || this.responseType === "text" ? this.responseText : this.responseType === "json" ? JSON.stringify(this.response) : `[${this.responseType}]`; }
        catch { t = null; }
        gui({ kind: "xhr", method: m.method, url: m.url, req_headers: m.headers, req_body: cat(anBody(bodyText(body) ?? ""), MAX_REQ),
          status: this.status, res_type: this.getResponseHeader("content-type") || "", res_body: cat(t, MAX_RES) });
      });
    }
    return XS.apply(this, arguments);
  };
})();
