// Launcher: choose between the built-in server on this computer and the firm's hosted server.
(function () {
  var invoke = window.__TAURI__ && window.__TAURI__.core ? window.__TAURI__.core.invoke : null;
  var statusEl = document.getElementById('status');
  var localBtn = document.getElementById('open-local');
  var serverForm = document.getElementById('server-form');
  var serverInput = document.getElementById('server-url');
  var remember = document.getElementById('remember');

  function setStatus(text, kind) {
    statusEl.textContent = text || '';
    statusEl.className = 'status' + (kind ? ' ' + kind : '');
  }

  function busy(on) {
    localBtn.disabled = on;
    serverForm.querySelector('button').disabled = on;
  }

  function openLocal() {
    busy(true);
    setStatus('Starting LawPractice on this computer… The first start can take up to a minute.', 'busy');
    invoke('open_local', { remember: remember.checked }).then(function (url) {
      window.location.replace(url);
    }).catch(function (err) {
      busy(false);
      setStatus(String(err), 'error');
    });
  }

  if (!invoke) {
    setStatus('Open this screen from the LawPractice desktop app.', 'error');
    busy(true);
    return;
  }

  localBtn.addEventListener('click', openLocal);

  serverForm.addEventListener('submit', function (e) {
    e.preventDefault();
    busy(true);
    setStatus('Connecting…', 'busy');
    invoke('open_server', { url: serverInput.value, remember: remember.checked }).then(function (url) {
      window.location.replace(url);
    }).catch(function (err) {
      busy(false);
      setStatus(String(err), 'error');
    });
  });

  invoke('launcher_info').then(function (info) {
    if (info.config.server_url) { serverInput.value = info.config.server_url; }
    document.getElementById('foot').textContent =
      'Version ' + info.version + ' · Data on this computer is kept in ' + info.data_dir;
    if (!info.backend_available) {
      localBtn.disabled = true;
      document.getElementById('local-note').textContent =
        'Not available in this copy of the app. Reinstall LawPractice to use it.';
    } else if (info.auto_start_local) {
      openLocal();
    }
  }).catch(function (err) { setStatus(String(err), 'error'); });
})();
