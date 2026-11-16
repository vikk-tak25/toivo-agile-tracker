'use strict';
const statuses = {todo: 'Todo / Backlog', doing: 'Doing', done: 'Done'};
const board = document.querySelector('#board');
const editor = document.querySelector('#editor');
const form = document.querySelector('#story-form');
const details = document.querySelector('#details');
let stories = [];
let draggedId = null;
let reorderPending = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, className = 'quiet') {
  const node = element('button', text, className);
  node.type = 'button';
  node.addEventListener('click', () => Promise.resolve().then(action).catch(showError));
  return node;
}
function showError(error, target = document.querySelector('#error')) {
  target.textContent = error.message;
  target.hidden = false;
}
async function api(path, method = 'GET', data) {
  const response = await fetch('/api/stories' + path, {
    method, headers: {'Content-Type': 'application/json'},
    ...(data === undefined ? {} : {body: JSON.stringify(data)})
  });
  if (response.status === 204) return null;
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Päring ebaõnnestus.');
  return result;
}
async function refresh() {
  stories = await api('');
  document.querySelector('#error').hidden = true;
  render();
}
function render() {
  board.replaceChildren();
  document.querySelector('#summary').textContent = `${stories.length} lugu · ${stories.reduce((n, s) => n + s.points, 0)} punkti kokku`;
  const query = document.querySelector('#search').value.toLocaleLowerCase();
  for (const [status, title] of Object.entries(statuses)) {
    const all = stories.filter(s => s.status === status);
    const visible = all.filter(s => (s.title + ' ' + s.description).toLocaleLowerCase().includes(query));
    const column = element('section', undefined, `column ${status}`);
    column.dataset.status = status;
    column.setAttribute('aria-label', title);
    const heading = element('h3');
    heading.append(element('span', '', 'dot'), element('span', title), element('span', String(visible.length), 'count'));
    column.append(heading);
    if (status === 'todo' && !query) {
      column.addEventListener('dragover', event => {
        if (draggedId === null || reorderPending) return;
        event.preventDefault(); event.dataTransfer.dropEffect = 'move';
      });
      column.addEventListener('drop', event => {
        if (draggedId === null || reorderPending) return;
        event.preventDefault();
        const target = event.target.closest('.card');
        moveBacklog(draggedId, target ? Number(target.dataset.id) : null).catch(showError);
        draggedId = null;
      });
    }
    const list = element('div', undefined, 'cards');
    for (const story of visible) list.append(card(story));
    if (!visible.length) list.append(element('p', query ? 'Otsingule vastavaid lugusid pole.' : 'Siin on ruumi järgmisele loole.', 'empty'));
    column.append(list, element('p', `${all.reduce((n, s) => n + s.points, 0)} punkti`, 'column-footer'));
    board.append(column);
  }
}
function card(story) {
  const node = element('article', undefined, 'card');
  node.dataset.id = story.id;
  if (story.status === 'todo' && !document.querySelector('#search').value) {
    node.draggable = true;
    node.title = 'Lohista backlogi järjekorra muutmiseks';
    node.addEventListener('dragstart', event => {
      if (reorderPending) { event.preventDefault(); return; }
      draggedId = story.id;
      event.dataTransfer.setData('text/plain', String(story.id));
      event.dataTransfer.effectAllowed = 'move';
      node.classList.add('dragging');
    });
    node.addEventListener('dragend', () => { draggedId = null; node.classList.remove('dragging'); });
  }
  const meta = element('div', undefined, 'meta');
  meta.append(element('span', `LUGU #${story.id}`), element('span', `${story.points} p`, 'points'));
  node.append(meta, element('h4', story.title));
  if (story.description) node.append(element('p', story.description));
  node.append(element('p', `${story.acceptanceCriteria.length} vastuvõtutingimust · ${story.comments.length} kommentaari`));
  const actions = element('div', undefined, 'card-actions');
  actions.append(button('Ava', () => openDetails(story.id)), button('Muuda', () => editStory(story)));
  const select = element('select');
  select.setAttribute('aria-label', `Loo ${story.id} staatus`);
  for (const [value, text] of Object.entries(statuses)) {
    const option = element('option', text);
    option.value = value;
    select.append(option);
  }
  select.value = story.status;
  select.addEventListener('change', async () => {
    select.disabled = true;
    try { await api(`/${story.id}/status`, 'PATCH', {status: select.value}); await refresh(); }
    catch (error) { select.value = story.status; showError(error); }
    finally { select.disabled = false; }
  });
  actions.append(select);
  node.append(actions);
  if (story.status === 'todo' && !document.querySelector('#search').value) {
    const order = stories.filter(s => s.status === 'todo').map(s => s.id);
    const index = order.indexOf(story.id);
    const controls = element('div', undefined, 'order-actions');
    const up = button('↑ Üles', () => moveBacklog(story.id, order[index - 1]));
    const down = button('↓ Alla', () => moveBacklog(story.id, order[index + 2] ?? null));
    up.setAttribute('aria-label', `Liiguta lugu ${story.id} üles`);
    down.setAttribute('aria-label', `Liiguta lugu ${story.id} alla`);
    up.disabled = index === 0 || reorderPending;
    down.disabled = index === order.length - 1 || reorderPending;
    controls.append(element('span', '⠿ Lohista'), up, down);
    node.append(controls);
  }
  return node;
}
async function moveBacklog(id, beforeId) {
  if (reorderPending || id === beforeId) return;
  const ids = stories.filter(s => s.status === 'todo' && s.id !== id).map(s => s.id);
  const index = beforeId === null ? ids.length : ids.indexOf(beforeId);
  if (index < 0) return;
  ids.splice(index, 0, id);
  reorderPending = true;
  try { await api('/reorder', 'PATCH', {ids}); await refresh(); }
  catch (error) { await refresh(); throw error; }
  finally { reorderPending = false; render(); }
}
function editStory(story = null) {
  form.reset();
  form.elements.id.value = story?.id ?? '';
  form.elements.title.value = story?.title ?? '';
  form.elements.description.value = story?.description ?? '';
  form.elements.points.value = story?.points ?? '';
  form.elements.status.value = story?.status ?? 'todo';
  form.elements.criteria.value = story?.acceptanceCriteria.join('\n') ?? '';
  document.querySelector('#editor-title').textContent = story ? `Muuda lugu #${story.id}` : 'Uus lugu';
  document.querySelector('#form-error').hidden = true;
  editor.showModal();
  form.elements.title.focus();
}
async function openDetails(id) {
  const story = await api(`/${id}`);
  const content = document.querySelector('#detail-content');
  content.replaceChildren(element('p', `LUGU #${id} · ${statuses[story.status]} · ${story.points} punkti`, 'eyebrow'), element('h2', story.title), element('p', story.description));
  content.append(element('h3', 'Vastuvõtutingimused'));
  const criteria = element('ul');
  story.acceptanceCriteria.forEach(c => criteria.append(element('li', c)));
  content.append(criteria, element('p', `Loodud ${new Date(story.createdAt).toLocaleString('et-EE')} · Muudetud ${new Date(story.updatedAt).toLocaleString('et-EE')}`));
  const actions = element('div', undefined, 'actions');
  actions.append(button('Muuda', () => { details.close(); editStory(story); }), button('Kustuta lugu', async () => {
    if (!window.confirm(`Kustuta lugu #${id} koos kommentaaridega?`)) return;
    await api(`/${id}`, 'DELETE'); details.close(); await refresh();
  }, 'danger'));
  content.append(actions, element('h3', 'Arutelu'));
  if (!story.comments.length) content.append(element('p', 'Kommentaare veel pole.'));
  for (const comment of story.comments) {
    const item = element('div', undefined, 'comment');
    const time = element('time', new Date(comment.createdAt).toLocaleString('et-EE'));
    time.dateTime = comment.createdAt;
    item.append(time, element('p', comment.text));
    content.append(item);
  }
  const commentForm = element('form');
  const label = element('label', 'Lisa kommentaar');
  const text = element('textarea');
  text.required = true; text.maxLength = 10000; text.rows = 3;
  label.append(text);
  const submit = element('button', 'Lisa kommentaar');
  submit.type = 'submit';
  const errorBox = element('p'); errorBox.role = 'alert'; errorBox.hidden = true;
  commentForm.append(label, errorBox, submit);
  commentForm.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true;
    try { await api(`/${id}/comments`, 'POST', {text: text.value}); await refresh(); await openDetails(id); }
    catch (error) { showError(error, errorBox); }
    finally { submit.disabled = false; }
  });
  content.append(commentForm);
  if (!details.open) details.showModal();
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  const submit = form.querySelector('[type=submit]'); submit.disabled = true;
  const data = {title: form.elements.title.value, description: form.elements.description.value,
    points: Number(form.elements.points.value), status: form.elements.status.value,
    acceptanceCriteria: form.elements.criteria.value.split('\n').map(s => s.trim()).filter(Boolean)};
  try {
    if (!form.elements.points.value.trim() || !Number.isInteger(data.points)) throw new Error('Punktid peavad olema mittetühjad täisarvud.');
    const id = form.elements.id.value;
    await api(id ? `/${id}` : '', id ? 'PUT' : 'POST', data);
    editor.close(); await refresh();
  } catch (error) { showError(error, document.querySelector('#form-error')); }
  finally { submit.disabled = false; }
});
document.querySelector('#new-story').addEventListener('click', () => editStory());
for (const id of ['close-editor', 'cancel-editor']) document.getElementById(id).addEventListener('click', () => editor.close());
document.querySelector('#close-details').addEventListener('click', () => details.close());
document.querySelector('#search').addEventListener('input', render);
refresh().catch(showError);
