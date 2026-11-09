/* authui: mờ nút theo quyền và hiện danh tính người đang đăng nhập ở cuối .topbar.

   Nguyên tắc: ĐÂY CHỈ LÀ LỚP TRANG TRÍ. Mọi endpoint đã bị server gác bằng
   auth.guard(); ẩn nút chỉ để người dùng không bấm vào thứ chắc chắn 403.
   Không bao giờ coi lớp này là bảo mật — ai cũng xoá được class trong devtool. */
const AUTHUI = (() => {
  const LV = { none: 0, view: 1, edit: 2 };
  let me = { auth: false, caps: {} };

  const can = (cap, need) => LV[me.caps[cap] || 'none'] >= LV[need || 'view'];

  /* Phần tử khai quyền bằng data-cap="listing.export" và data-need="edit". */
  function apply(root) {
    (root || document).querySelectorAll('[data-cap]').forEach((el) => {
      const ok = can(el.dataset.cap, el.dataset.need);
      if (ok) { el.removeAttribute('data-denied'); return; }
      el.setAttribute('data-denied', '1');
      if ('disabled' in el) el.disabled = true;
      const tip = `Vai trò ${me.role || 'khách'} không có quyền này`;
      el.title = tip;
      /* input[type=file] nằm trong <label> mà bị ẩn: input disabled thì label
         bấm không ăn, nhưng label vẫn TRÔNG như bấm được. Mờ luôn cái label. */
      const lab = el.closest('label');
      if (lab && lab !== el) { lab.setAttribute('data-denied', '1'); lab.title = tip; }
    });
  }

  function paintIdentity() {
    const box = document.querySelector('.topbar');
    if (!box || !me.auth) return;              // auth tắt → không hiện gì
    if (document.getElementById('whoami')) return;
    const s = document.createElement('span');
    s.id = 'whoami';
    s.className = 'whoami';
    s.innerHTML = me.user
      ? `<b>${(me.user.email || '').split('@')[0]}</b><i>${me.role}</i>`
        + `<a href="/logout" title="Đăng xuất">thoát</a>`
      : `<a href="/login" class="btn">Đăng nhập</a>`;
    box.appendChild(s);
  }

  async function boot() {
    try {
      const r = await fetch('/api/me');
      me = await r.json();
    } catch (_) { /* server chết thì để nguyên, các fetch khác sẽ tự báo */ }
    paintIdentity();
    apply();
    return me;
  }

  return { boot, apply, can, get me() { return me; } };
})();
