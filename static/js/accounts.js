(() => {
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const $ = selector => document.querySelector(selector);
  async function post(url, body) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    if (response.redirected) { location.href = response.url; throw new Error('Vuelve a iniciar sesión en el administrador.'); }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'No se pudo completar la acción.');
    return result;
  }

  const card = $('#codex-card'), say = text => { $('#codex-status').textContent = text; };
  $('#codex-start')?.addEventListener('click', async () => {
    // Open the tab synchronously so the browser does not block it as a pop-up.
    const tab = window.open('about:blank', '_blank');
    try {
      const result = await post(card.dataset.url, { action: 'start' });
      if (tab) { tab.opener = null; tab.location.href = result.url; } else { window.open(result.url, '_blank', 'noopener'); }
      $('#codex-paste').hidden = false;
      $('#codex-callback').value = '';
      $('#codex-callback').focus();
      say(result.message);
    } catch (error) { if (tab) tab.close(); say(error.message); }
  });
  $('#codex-complete')?.addEventListener('click', async () => {
    const button = $('#codex-complete');
    button.disabled = true;
    try {
      const result = await post(card.dataset.url, { action: 'complete', callback: $('#codex-callback').value });
      $('#codex-callback').value = '';
      say(result.message);
      setTimeout(() => location.reload(), 4000);
    } catch (error) { say(error.message); button.disabled = false; }
  });
  const disconnect = $('#codex-disconnect');
  if (disconnect) disconnect.addEventListener('click', async () => {
    if (!confirm('¿Desconectar ChatGPT? Se borrará la credencial guardada en TokenDash.')) return;
    try { say((await post(card.dataset.url, { action: 'disconnect' })).message); setTimeout(() => location.reload(), 2500); }
    catch (error) { say(error.message); }
  });

  // Claude: the server's own client reads the limits. There is only one way.
  const claudeButton = $('#claude-client-enable');
  if (claudeButton) claudeButton.addEventListener('click', async () => {
    const status = $('#claude-client-status');
    claudeButton.disabled = true;
    try {
      const result = await post(claudeButton.dataset.url, { action: 'enable' });
      status.textContent = result.message;
      // The session is not connected yet: keep the page so the operator can
      // read the guide and finish the sign-in.
      if (!result.needs_session) setTimeout(() => location.reload(), 2500);
    } catch (error) { status.textContent = error.message; }
    finally { claudeButton.disabled = false; }
  });
  // The worker's client keeps the session: ask it to report the state again.
  const sessionButton = $('#claude-session-check');
  if (sessionButton) sessionButton.addEventListener('click', async () => {
    const status = $('#claude-session-status');
    sessionButton.disabled = true;
    try {
      status.textContent = (await post(sessionButton.dataset.url, { action: 'check' })).message;
      setTimeout(() => location.reload(), 3000);
    } catch (error) { status.textContent = error.message; }
    finally { sessionButton.disabled = false; }
  });

  // Copy buttons of the sign-in guide. The page may be served over plain HTTP in
  // the intranet, where navigator.clipboard is missing: fall back to a selection.
  async function copy(text, button) {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const area = Object.assign(document.createElement('textarea'), { value: text });
      document.body.append(area); area.select(); document.execCommand('copy'); area.remove();
    }
    const label = button.textContent;
    button.textContent = 'Copiado';
    setTimeout(() => { button.textContent = label; }, 1500);
  }
  document.querySelectorAll('.copy-command').forEach(button => button.addEventListener('click', () =>
    copy(button.previousElementSibling.textContent.trim(), button)));
  const guideCopy = $('#claude-guide-copy');
  if (guideCopy) guideCopy.addEventListener('click', () => {
    const steps = [...document.querySelectorAll('#claude-guide-steps > li')].map((step, index) => {
      const clone = step.cloneNode(true);
      clone.querySelectorAll('button').forEach(button => button.remove());
      // Commands go on their own indented line so they can be pasted as they are.
      clone.querySelectorAll('.command, .browser-hint').forEach(node => { node.textContent = `\n${node.matches('.command') ? '\u0000' : ''}${node.textContent.trim()}\n`; });
      const lines = clone.textContent.split('\n').map(line => line.replace(/\s+/g, ' ').trim()).filter(Boolean)
        .map(line => line.startsWith('\u0000') ? `    ${line.slice(1)}` : line);
      return `${index + 1}. ${lines.join('\n')}`;
    });
    copy(`Vincular Claude con el servidor TokenDash (una sola vez)\n\n${steps.join('\n\n')}\n\nNo usar «claude setup-token»: no puede leer la cuota.`, guideCopy);
  });
})();
