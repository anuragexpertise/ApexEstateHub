// op_progress_trigger.js
// Opens the progress modal the instant a database-intensive action is triggered.
//
// A Dash callback only runs when every one of its Inputs exists in the layout, and these buttons live on different
// pages, so one callback listing them all would never fire. Instead one delegated listener recognises the action,
// stores its title, and clicks the hidden always-present #op-open-btn that the clientside callback listens to.
(function () {
  var TITLES = {
    'btn-fy-export': 'Preparing your report',
    'btn-xls-download': 'Preparing your download',
    'bulk-enroll-upload': 'Enrolling from your file',
    'bank-reconcile-upload': 'Reconciling the bank statement',
    'onb-seal': 'Sealing the annexes and issuing the Agreement',
    'upc-dep-run': 'Posting the depreciation fund',
    'onb-finalize-confirm': 'Saving the Setup Wizard',
    'onb-prepare': 'Checking the annexes',
    'onb-supp-build': 'Preparing the annexure',
    'onb-decl-apply': 'Applying the Declaration',
    'onb-enrol-done': 'Completing enrollment',
    'fy-close-reserve-submit': 'Closing the financial year',
    'fy-lock-submit': 'Locking the financial year'
  };
  var UPLOADS = ['bulk-enroll-upload', 'bank-reconcile-upload'];

  function titleFor(id) {
    if (!id) { return null; }
    var parsed = null;
    if (id.charAt(0) === '{') { try { parsed = JSON.parse(id); } catch (e) { return null; } }
    if (parsed) {
      if (parsed.type === 'form-submit') {
        return parsed.card_id === 'form_master_society_new' ? 'Registering the society' : null;
      }
      return TITLES[parsed.type] || null;
    }
    return TITLES[id] || null;
  }

  function open(title) {
    window.__ehOpTitle = title;
    var btn = document.getElementById('op-open-btn');
    if (btn) { btn.click(); }
  }

  // buttons: walk up from the click target (an icon or label inside the button) to the element that carries the id
  document.addEventListener('click', function (e) {
    var el = e.target;
    while (el && el !== document.body) {
      if (el.id) {
        var t = titleFor(el.id);
        if (t && UPLOADS.indexOf(el.id) === -1) {
          if (el.disabled || el.getAttribute('aria-disabled') === 'true') { return; }
          open(t);
          return;
        }
      }
      el = el.parentNode;
    }
  }, true);

  // uploads: the action starts when a file is chosen or dropped, not when the picker is opened
  function uploadHost(node) {
    while (node && node !== document.body) {
      if (node.id && UPLOADS.indexOf(node.id) !== -1) { return node; }
      node = node.parentNode;
    }
    return null;
  }
  document.addEventListener('change', function (e) {
    var host = uploadHost(e.target);
    if (host && e.target.files && e.target.files.length) { open(TITLES[host.id]); }
  }, true);
  document.addEventListener('drop', function (e) {
    var host = uploadHost(e.target);
    if (host) { open(TITLES[host.id]); }
  }, true);
})();
