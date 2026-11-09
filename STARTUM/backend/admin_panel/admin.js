(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const labels = {
    users: 'Telegram foydalanuvchilari', courses: 'Faol kurslar', teachers: 'Ustozlar',
    applications: 'Bot arizalari', new_applications: 'Yangi bot arizalari',
    applications_in_review: 'Ko‘rib chiqilmoqda', applications_contacted: 'Bog‘lanilgan', applications_accepted: 'Qabul qilingan', applications_rejected: 'Rad etilgan',
    web_applications: 'Sayt arizalari', new_web_applications: 'Yangi sayt arizalari', messages: 'Yangi murojaatlar',
    resources: 'Faol materiallar', tests: 'Faol testlar', notifications_pending: 'Navbatdagi Telegram xabarlari', notifications_failed: 'Yetkazilmagan xabarlar'
  };
  const statusLabels = { new: 'Yangi', in_review: 'Ko‘rib chiqilmoqda', contacted: 'Bog‘lanildi', accepted: 'Qabul qilindi', rejected: 'Rad etildi', in_progress: 'Ko‘rib chiqilmoqda', closed: 'Yopildi (eski holat)' };
  const viewTitles = { overview: 'Umumiy ko‘rinish', applications: 'Arizalarni boshqarish', users: 'Foydalanuvchilar', catalog: 'Kurslar va ustozlar', messages: 'Murojaatlar', notifications: 'Telegram xabarlari', resources: 'O‘quv materiallari', 'quiz-results': 'Test natijalari', audit: 'Amallar tarixi', groups: 'Ta’lim guruhlari', calendar: 'Akademik kalendar', exports: 'Hisobot eksporti', accounts: 'Administratorlar' };
  const roleLabels = { ceo: 'CEO', senior_admin: 'Katta administrator', junior_admin: 'Kichik administrator' };
  let currentView = 'overview';
  let currentRole = '';
  let currentUsername = '';
  let applicationOffset = 0;
  let userOffset = 0;
  let selectedUserId = 0;
  let catalogCache = { courses: [], teachers: [] };
  let calendarCache = [];
  let currentDiagnostics = null;

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  }
  function showMessage(message, isError = false) {
    const el = $('#globalMessage');
    el.textContent = message || '';
    el.style.color = isError ? 'var(--danger)' : 'var(--mint)';
  }
  async function api(path, options = {}) {
    const headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    if (options.method && !['GET', 'HEAD'].includes(options.method.toUpperCase())) headers['X-STARTUM-Admin'] = '1';
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers });
    const content = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(content.detail || `So‘rov bajarilmadi (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return content;
  }
  function setConnected(isConnected) {
    const el = $('#connectionState');
    el.textContent = isConnected ? 'Backend ulangan' : 'Backend bilan aloqa yo‘q';
    el.style.color = isConnected ? 'var(--mint)' : 'var(--danger)';
  }
  function showLogin(message = '') {
    $('#sidebar')?.classList.remove('open');
    document.body.classList.remove('admin-nav-open');
    if ($('#sidebarBackdrop')) $('#sidebarBackdrop').hidden = true;
    $('#mobileMenu')?.setAttribute('aria-expanded', 'false');
    $('#workspace').hidden = true;
    $('#loginStage').hidden = false;
    $('#logoutButton').hidden = true;
    $('#appShell')?.classList.add('is-logged-out');
    $('#loginMessage').textContent = message;
  }
  function applyRoleVisibility() {
    $$('[data-role-allow]').forEach(element => {
      const allowed = element.dataset.roleAllow.split(',').map(value => value.trim());
      element.hidden = !allowed.includes(currentRole);
    });
    $$('[data-nav-group]').forEach(group => {
      group.hidden = !group.querySelector('[data-view]:not([hidden])');
    });
    $$('[data-write-roles]').forEach(element => {
      const allowed = element.dataset.writeRoles.split(',').map(value => value.trim());
      element.hidden = !allowed.includes(currentRole);
    });
    const roleSelect = $('#accountRole');
    if (roleSelect) {
      const seniorOption = roleSelect.querySelector('option[value="senior_admin"]');
      if (seniorOption) seniorOption.hidden = currentRole !== 'ceo';
      if (currentRole === 'senior_admin') roleSelect.value = 'junior_admin';
    }
  }
  function showWorkspace(session) {
    currentUsername = session.username || '';
    currentRole = session.role || '';
    $('#appShell')?.classList.remove('is-logged-out');
    $('#loginStage').hidden = true;
    $('#workspace').hidden = false;
    $('#logoutButton').hidden = false;
    $('#welcomeMessage').textContent = `Tizimga kirilgan: ${currentUsername} · ${session.role_label || roleLabels[currentRole] || currentRole}. Ma’lumotlar joriy bazadan olinadi.`;
    applyRoleVisibility();
    const selfPasswordForm = $('#selfPasswordForm');
    const selfPasswordNote = $('#ceoPasswordNote');
    if (selfPasswordForm) selfPasswordForm.hidden = currentRole === 'ceo';
    if (selfPasswordNote) selfPasswordNote.hidden = currentRole !== 'ceo';
    if ($(`[data-view="${currentView}"]`)?.hidden) currentView = 'overview';
    setView(currentView);
  }
  function setView(view) {
    currentView = view;
    $('#pageTitle').textContent = viewTitles[view] || viewTitles.overview;
    $$('[data-panel]').forEach(panel => {
      const allowed = !panel.dataset.roleAllow || panel.dataset.roleAllow.split(',').map(value => value.trim()).includes(currentRole);
      panel.hidden = panel.dataset.panel !== view || !allowed;
    });
    $$('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
    if (view === 'applications') loadApplications();
    if (view === 'users') loadUsers();
    if (view === 'catalog') loadCatalog();
    if (view === 'messages') loadMessages();
    if (view === 'resources') loadResources();
    if (view === 'quiz-results') loadQuizResults();
    if (view === 'notifications') loadNotifications();
    if (view === 'groups') loadEducationGroups();
    if (view === 'calendar') loadCalendar();
    if (view === 'exports') applyRoleVisibility();
    if (view === 'audit') loadAudit();
    if (view === 'accounts') loadAccounts();
  }
  function statCard(key, value) {
    return `<article class="stat-card"><div class="stat-label">${escapeHTML(labels[key] || key)}</div><div class="stat-value">${Number(value) || 0}</div><div class="stat-note">Joriy ma’lumotlar bazasi</div></article>`;
  }
  function statusSelect(source, id, current) {
    const options = Object.entries(statusLabels).map(([value, text]) => `<option value="${value}" ${value === current ? 'selected' : ''}>${text}</option>`).join('');
    return `<select class="status-select" data-status-source="${source}" data-status-id="${Number(id)}" aria-label="Ariza holatini o‘zgartirish">${options}</select>`;
  }
  function applicationsHTML(items, source) {
    if (!items.length) return '<div class="empty-state">Bu filtr bo‘yicha ariza topilmadi.</div>';
    const rows = items.map(item => {
      const userLabel = source === 'website' ? item.telegram_username : (item.username ? `@${item.username}` : `ID ${item.telegram_id}`);
      const when = item.created_at ? new Date(item.created_at).toLocaleString('uz-UZ') : '—';
      const rowId = Number(item.id);
      const detailKey = `${source}-${rowId}`;
      const optionalApplicationDetails = [
        item.level ? `<div><span>Daraja</span><b>${escapeHTML(item.level)}</b></div>` : '',
        item.preferred_time ? `<div><span>Qulay vaqt</span><b>${escapeHTML(item.preferred_time)}</b></div>` : '',
      ].join('');
      const detail = `<tr class="application-detail-row" data-application-detail-row="${detailKey}" hidden><td colspan="5"><div class="application-full-details"><div><span>Arizachi</span><b>${escapeHTML(item.full_name)}</b></div><div><span>Telefon</span><b>${escapeHTML(item.phone)}</b></div><div><span>Telegram</span><b>${escapeHTML(userLabel || '—')}</b></div><div><span>Kurs</span><b>${escapeHTML(item.course_name || '—')}</b></div>${optionalApplicationDetails}<div><span>Yuborilgan</span><b>${escapeHTML(when)}</b></div><div class="application-full-message"><span>Izoh</span><p>${escapeHTML(item.message || 'Izoh qoldirilmagan.')}</p></div><div class="application-status-history" data-status-history="${detailKey}"><span>Holat tarixi yuklanmagan.</span></div></div></td></tr>`;
      const legacyLevel = item.level ? `<small>Daraja: ${escapeHTML(item.level)}</small>` : '';
      const main = `<tr><td data-mobile-label="Ariza"><b>#${rowId}</b><small>${escapeHTML(when)}</small><button class="button subtle compact" type="button" data-open-application="${rowId}" data-application-source="${source}" aria-expanded="false">To‘liq ariza</button></td><td data-mobile-label="Arizachi"><b>${escapeHTML(item.full_name)}</b><small>${escapeHTML(item.phone)} · ${escapeHTML(userLabel)}</small></td><td data-mobile-label="Kurs">${escapeHTML(item.course_name || '—')}${legacyLevel}</td><td data-mobile-label="Holat"><span class="pill">${escapeHTML(statusLabels[item.status] || item.status)}</span></td><td data-mobile-label="Yangilash">${statusSelect(source, rowId, item.status)}</td></tr>`;
      return main + detail;
    }).join('');
    return `<table class="data-table" data-mobile-cards="true"><thead><tr><th>Ariza</th><th>Arizachi</th><th>Kurs</th><th>Holat</th><th>Yangilash</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  async function loadStats() {
    const data = await api('/api/admin/overview');
    const preferred = ['users','courses','teachers','new_web_applications','new_applications','applications_in_review','applications_contacted','applications_accepted','applications_rejected','notifications_pending','notifications_failed','resources','tests','web_applications','applications','messages'];
    $('#statsGrid').innerHTML = preferred.filter(key => key in data).map(key => statCard(key, data[key])).join('');
  }
  async function loadApplications() {
    const source = $('#sourceFilter').value;
    const status = $('#statusFilter').value;
    const limit = currentView === 'overview' ? 5 : 20;
    const search = currentView === 'overview' ? '' : ($('#applicationSearch')?.value || '').trim();
    const query = new URLSearchParams({ source, limit: String(limit), offset: String(currentView === 'overview' ? 0 : applicationOffset), q: search });
    if (status) query.set('status', status);
    try {
      const data = await api(`/api/admin/applications?${query.toString()}`);
      const html = applicationsHTML(data.items, source);
      if (currentView === 'overview') $('#recentApplications').innerHTML = html;
      else {
        $('#applicationsTable').innerHTML = html;
        const pager = $('#applicationPagination');
        pager.hidden = false;
        const total = Number(data.total) || 0;
        const from = total ? applicationOffset + 1 : 0;
        const to = Math.min(applicationOffset + data.items.length, total);
        $('#paginationSummary').textContent = `${from}–${to} / ${total} ta ariza`;
        $('#previousPage').disabled = applicationOffset <= 0;
        $('#nextPage').disabled = !data.has_more;
      }
    } catch (error) {
      if (currentView === 'overview') $('#recentApplications').innerHTML = '<div class="empty-state">Ma’lumotni yuklab bo‘lmadi.</div>';
      else $('#applicationsTable').innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }
  async function exportApplications() {
    const button = $('#exportApplications');
    if (!button || !['ceo', 'senior_admin'].includes(currentRole)) {
      showMessage('CSV eksporti uchun CEO yoki Senior Admin ruxsati kerak.', true);
      return;
    }
    const query = new URLSearchParams({ source: $('#sourceFilter').value });
    const status = $('#statusFilter').value;
    const search = ($('#applicationSearch')?.value || '').trim();
    if (status) query.set('status', status);
    if (search) query.set('q', search);
    button.disabled = true;
    const previousLabel = button.textContent;
    button.textContent = 'Tayyorlanmoqda…';
    try {
      const response = await fetch(`/api/admin/applications/export.csv?${query.toString()}`, {
        credentials: 'same-origin',
        headers: { Accept: 'text/csv' },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Eksport bajarilmadi (${response.status}).`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `startum-arizalar-${query.get('source')}-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      const count = response.headers.get('X-Export-Count') || '0';
      const capped = response.headers.get('X-Export-Truncated') === 'true';
      showMessage(`${count} ta ariza CSV fayliga tayyorlandi.${capped ? ' Eksport xavfsizlik uchun 5 000 ta yozuv bilan cheklandi.' : ''}`);
    } catch (error) {
      showMessage(error.message || 'CSV eksportida xatolik yuz berdi.', true);
    } finally {
      button.disabled = false;
      button.textContent = previousLabel;
    }
  }

  function messagesHTML(items) {
    if (!items.length) return '<div class="empty-state">Bu filtr bo‘yicha murojaat topilmadi.</div>';
    const rows = items.map(item => {
      const fullName = [item.first_name, item.last_name].filter(Boolean).join(' ').trim() || 'Telegram foydalanuvchisi';
      const handle = item.username ? `@${item.username}` : `ID ${item.telegram_id}`;
      const when = item.created_at ? new Date(item.created_at).toLocaleString('uz-UZ') : '—';
      const status = item.status === 'answered' ? 'Javob berilgan' : 'Yangi';
      return `<tr><td><b>#${Number(item.id)}</b><small>${escapeHTML(when)}</small></td><td><b>${escapeHTML(fullName)}</b><small>${escapeHTML(handle)}</small></td><td>${escapeHTML(item.topic || '—')}</td><td class="message-cell">${escapeHTML(item.message_text || '')}</td><td><span class="pill ${item.status === 'answered' ? 'muted-pill' : ''}">${status}</span></td></tr>`;
    }).join('');
    return `<table class="data-table"><thead><tr><th>Murojaat</th><th>Foydalanuvchi</th><th>Mavzu</th><th>Xabar</th><th>Holat</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  async function loadMessages() {
    const status = $('#messageStatusFilter')?.value || '';
    const q = ($('#messageSearch')?.value || '').trim();
    const query = new URLSearchParams({ limit: '100' });
    if (status) query.set('status', status);
    if (q) query.set('q', q);
    $('#messagesTable').innerHTML = '<div class="empty-state">Murojaatlar yuklanmoqda…</div>';
    try {
      const data = await api(`/api/admin/messages?${query.toString()}`);
      $('#messagesTable').innerHTML = messagesHTML(data.items || []);
      $('#messageSummary').textContent = `${(data.items || []).length} ta murojaat ko‘rsatildi`;
    } catch (error) {
      $('#messagesTable').innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      $('#messageSummary').textContent = 'Yuklash amalga oshmadi';
      showMessage(error.message, true);
    }
  }
  async function loadCatalog() {
    try {
      const data = await api('/api/admin/catalog');
      catalogCache = {
        courses: Array.isArray(data.courses) ? data.courses : [],
        teachers: Array.isArray(data.teachers) ? data.teachers : [],
      };
      const canManage = ['ceo', 'senior_admin'].includes(currentRole);
      $('#coursesTable').innerHTML = catalogCache.courses.length ? `<table class="data-table"><thead><tr><th>Kurs</th><th>Turi</th><th>Holat</th>${canManage ? '<th>Amallar</th>' : ''}</tr></thead><tbody>${catalogCache.courses.map(c => `<tr><td><b>${escapeHTML(c.name_uz)}</b><small>${escapeHTML(c.slug)}</small></td><td>${escapeHTML(c.kind)}</td><td><span class="pill ${c.active ? '' : 'muted-pill'}">${c.active ? 'Faol' : 'Nofaol'}</span></td>${canManage ? `<td><button class="button subtle compact" type="button" data-edit-kind="course" data-edit-id="${Number(c.id)}">Tahrirlash</button> <button class="button subtle compact" type="button" data-toggle-kind="course" data-toggle-id="${Number(c.id)}" data-toggle-active="${c.active ? '1' : '0'}">${c.active ? 'Faolsizlantirish' : 'Faollashtirish'}</button></td>` : ''}</tr>`).join('')}</tbody></table>` : '<div class="empty-state">Kurslar topilmadi.</div>';
      $('#teachersTable').innerHTML = catalogCache.teachers.length ? `<table class="data-table"><thead><tr><th>Ustoz</th><th>Fan</th>${canManage ? '<th>Amallar</th>' : ''}</tr></thead><tbody>${catalogCache.teachers.map(t => `<tr><td><b>${escapeHTML(t.full_name)}</b><small>${escapeHTML(t.experience || '')}</small><small><span class="pill ${t.active ? '' : 'muted-pill'}">${t.active ? 'Faol' : 'Nofaol'}</span></small></td><td>${escapeHTML(t.subject)}</td>${canManage ? `<td><button class="button subtle compact" type="button" data-edit-kind="teacher" data-edit-id="${Number(t.id)}">Tahrirlash</button> <button class="button subtle compact" type="button" data-toggle-kind="teacher" data-toggle-id="${Number(t.id)}" data-toggle-active="${t.active ? '1' : '0'}">${t.active ? 'Faolsizlantirish' : 'Faollashtirish'}</button></td>` : ''}</tr>`).join('')}</tbody></table>` : '<div class="empty-state">Ustozlar topilmadi.</div>';
    } catch (error) { showMessage(error.message, true); }
  }
  const resourceLabels = { book: 'Kitob', vocabulary: 'Lug‘at', movie: 'Kino / video', music: 'Musiqa', quiz: 'Test' };
  async function loadResources() {
    try {
      const [resourceData, catalogData] = await Promise.all([
        api('/api/admin/resources'), api('/api/admin/catalog')
      ]);
      catalogCache.courses = Array.isArray(catalogData.courses) ? catalogData.courses : [];
      const activeCourses = catalogCache.courses.filter(course => Boolean(course.active));
      const courseSelect = $('#resourceCourse');
      if (courseSelect) {
        const previous = courseSelect.value;
        courseSelect.innerHTML = '<option value="">Yo‘nalishni tanlang</option>' + activeCourses.map(course =>
          `<option value="${Number(course.id)}">${escapeHTML(course.icon || '📚')} ${escapeHTML(course.name_uz)}</option>`
        ).join('');
        if (activeCourses.some(course => String(course.id) === previous)) courseSelect.value = previous;
      }
      const allItems = Array.isArray(resourceData.items) ? resourceData.items : [];
      const filter = $('#resourceFilter')?.value || '';
      const items = allItems.filter(item => !filter || item.category === filter);
      $('#resourceSummary').textContent = `${items.length} ta material · ${allItems.filter(item => item.active).length} ta faol`;
      const canManage = ['ceo', 'senior_admin'].includes(currentRole);
      if (!items.length) {
        $('#resourcesTable').innerHTML = '<div class="empty-state">Bu filtrda material topilmadi. Ustoz yoki administrator material qo‘shishi mumkin.</div>';
        return;
      }
      $('#resourcesTable').innerHTML = `<table class="data-table"><thead><tr><th>Material</th><th>Yo‘nalish</th><th>Turi</th><th>Holat</th>${canManage ? '<th>Amallar</th>' : ''}</tr></thead><tbody>${items.map(item => {
        const status = Boolean(item.active);
        const contentType = item.media_type === 'url' ? 'Havola' : (item.media_type === 'text' ? 'Matn' : 'Fayl');
        return `<tr><td><b>${escapeHTML(item.title)}</b><small>${escapeHTML(item.description || item.content || '')}</small></td><td>${escapeHTML(item.course_name || '—')}</td><td>${escapeHTML(resourceLabels[item.category] || item.category)}<small>${contentType}</small></td><td><span class="pill ${status ? '' : 'muted-pill'}">${status ? 'Faol' : 'Nofaol'}</span></td>${canManage ? `<td><button class="button subtle compact" type="button" data-toggle-resource="${Number(item.id)}" data-toggle-active="${status ? '1' : '0'}">${status ? 'Faolsizlantirish' : 'Faollashtirish'}</button></td>` : ''}</tr>`;
      }).join('')}</tbody></table>`;
      applyRoleVisibility();
    } catch (error) {
      $('#resourcesTable').innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }

  function resetEditForm(form, clearStatus = true) {
    delete form.dataset.editId;
    form.reset();
    const kind = form.id === 'courseForm' ? 'course' : 'teacher';
    const details = form.closest('details');
    if (details) details.querySelector('summary').textContent = kind === 'course' ? '＋ Yangi kurs qo‘shish' : '＋ Ustoz qo‘shish';
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.textContent = kind === 'course' ? 'Kursni saqlash' : 'Ustozni saqlash';
    const cancel = form.querySelector('[data-cancel-edit]');
    if (cancel) cancel.hidden = true;
    const status = $(`[data-form-message="${kind}"]`);
    if (status && clearStatus) status.textContent = '';
  }
  function beginEdit(kind, id) {
    if (!['ceo', 'senior_admin'].includes(currentRole)) {
      showMessage('Bu amal uchun ruxsat yetarli emas.', true);
      return;
    }
    const collection = kind === 'course' ? catalogCache.courses : catalogCache.teachers;
    const item = collection.find(record => Number(record.id) === Number(id));
    const form = $(`#${kind}Form`);
    if (!item || !form) { showMessage('Tahrirlanadigan yozuv topilmadi.', true); return; }
    for (const field of form.elements) {
      if (field.name && Object.prototype.hasOwnProperty.call(item, field.name)) field.value = item[field.name] ?? '';
    }
    form.dataset.editId = String(id);
    const details = form.closest('details');
    if (details) {
      details.open = true;
      details.querySelector('summary').textContent = `${kind === 'course' ? 'Kurs' : 'Ustoz'}ni tahrirlash #${id}`;
    }
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.textContent = 'O‘zgarishlarni saqlash';
    const cancel = form.querySelector('[data-cancel-edit]');
    if (cancel) cancel.hidden = false;
    const status = $(`[data-form-message="${kind}"]`);
    if (status) { status.textContent = `#${id} yozuvi tahrirlash rejimida.`; status.style.color = 'var(--muted)'; }
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  const notificationStatusLabels = { pending: 'Navbatda', sent: 'Yuborildi', failed: 'Xatolik' };
  async function loadNotifications() {
    try {
      const status = $('#notificationFilter')?.value || '';
      const data = await api(`/api/admin/notifications?limit=100${status ? `&status=${encodeURIComponent(status)}` : ''}`);
      const items = Array.isArray(data.items) ? data.items : [];
      $('#notificationSummary').textContent = `${items.length} ta xabar ko‘rsatilmoqda`;
      if (!items.length) {
        $('#notificationsTable').innerHTML = '<div class="empty-state">Bu filtrda Telegram xabarlari yo‘q.</div>';
        return;
      }
      $('#notificationsTable').innerHTML = `<table class="data-table"><thead><tr><th>Xabar</th><th>Manba</th><th>Qabul qiluvchi</th><th>Holat</th><th>Urinish</th><th>Yaratildi</th><th>Amal</th></tr></thead><tbody>${items.map(item => {
        const statusClass = item.status === 'sent' ? '' : 'muted-pill';
        const source = item.source === 'website' ? 'Sayt arizasi' : 'Bot arizasi';
        const error = item.last_error ? `<small>Xato: ${escapeHTML(item.last_error)}</small>` : '';
        const retry = item.status === 'sent' ? '<span class="muted">—</span>' : `<button class="button subtle compact" type="button" data-retry-notification="${Number(item.id)}">↻ Qayta yuborish</button>`;
        return `<tr><td><b>#${Number(item.application_id)} · ${escapeHTML(item.applicant || 'Arizachi')}</b><small>${escapeHTML(item.course_name || '—')}</small>${error}</td><td>${source}<small>#${Number(item.id)}</small></td><td><code>${escapeHTML(item.recipient_telegram_id)}</code></td><td><span class="pill ${statusClass}">${escapeHTML(notificationStatusLabels[item.status] || item.status)}</span></td><td>${Number(item.attempts) || 0}</td><td>${escapeHTML(item.created_at ? new Date(item.created_at).toLocaleString('uz-UZ') : '—')}<small>${item.sent_at ? 'Yuborilgan: ' + escapeHTML(new Date(item.sent_at).toLocaleString('uz-UZ')) : ''}</small></td><td>${retry}</td></tr>`;
      }).join('')}</tbody></table>`;
    } catch (error) {
      $('#notificationsTable').innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }

  let educationGroupsCache = [];
  async function loadEducationGroups() {
    const groupTable = $('#educationGroupsTable');
    if (!groupTable) return;
    groupTable.innerHTML = '<div class="empty-state">Guruhlar yuklanmoqda…</div>';
    try {
      const [data, catalog] = await Promise.all([api('/api/admin/education/groups?limit=200'), api('/api/admin/catalog')]);
      educationGroupsCache = Array.isArray(data.items) ? data.items : [];
      const courses = Array.isArray(catalog.courses) ? catalog.courses.filter(item => item.active) : [];
      const courseOptions = '<option value="">Kursni tanlang</option>' + courses.map(item => `<option value="${Number(item.id)}">${escapeHTML(item.name_uz)}</option>`).join('');
      const courseSelect = $('#educationGroupCourse');
      if (courseSelect) { const selected = courseSelect.value; courseSelect.innerHTML = courseOptions; if (courses.some(item => String(item.id) === selected)) courseSelect.value = selected; }
      const groupOptions = '<option value="">Guruhni tanlang</option>' + educationGroupsCache.filter(item => item.status === 'active').map(item => `<option value="${Number(item.id)}">${escapeHTML(item.name)} · ${escapeHTML(item.course_name)}</option>`).join('');
      const groupSelect = $('#educationTeacherGroup');
      if (groupSelect) { const selected = groupSelect.value; groupSelect.innerHTML = groupOptions; if (educationGroupsCache.some(item => String(item.id) === selected)) groupSelect.value = selected; }
      $('#educationGroupSummary').textContent = `${educationGroupsCache.length} ta guruh`;
      if (!educationGroupsCache.length) groupTable.innerHTML = '<div class="empty-state">Hozircha guruh yaratilmagan.</div>';
      else groupTable.innerHTML = `<table class="data-table"><thead><tr><th>Guruh</th><th>Kurs</th><th>Jadval</th><th>O‘quvchilar</th><th>Taklif kodi</th><th>Holat</th></tr></thead><tbody>${educationGroupsCache.map(item => `<tr><td><b>${escapeHTML(item.name)}</b><small>#${Number(item.id)}</small></td><td>${escapeHTML(item.course_name || '—')}</td><td>${escapeHTML(item.schedule_text || '—')}</td><td>${Number(item.student_count) || 0}</td><td><code>${escapeHTML(item.invite_code || '—')}</code></td><td><span class="calendar-status ${item.status === 'active' ? 'published' : 'archived'}">${item.status === 'active' ? 'Faol' : 'Arxivlangan'}</span></td></tr>`).join('')}</tbody></table>`;
      const assignments = Array.isArray(data.assignments) ? data.assignments : [];
      $('#educationAssignmentSummary').textContent = `${assignments.length} ta faol tayinlov`;
      $('#educationAssignmentsTable').innerHTML = assignments.length ? `<table class="data-table"><thead><tr><th>Ustoz Telegram ID</th><th>Kurs</th><th>Guruh</th><th>Amal</th></tr></thead><tbody>${assignments.map(item => `<tr><td><code>${escapeHTML(item.telegram_id)}</code></td><td>${escapeHTML(item.course_name || '—')}</td><td>${escapeHTML(item.group_name || 'Kurs bo‘yicha barcha guruhlar')}</td><td><button class="button subtle compact" type="button" data-revoke-teacher-assignment="${Number(item.id)}">Bekor qilish</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">Hozircha ustoz tayinlovi yo‘q.</div>';
    } catch (error) {
      groupTable.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }
  $('#refreshGroups')?.addEventListener('click', loadEducationGroups);
  $('#educationGroupForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!['ceo', 'senior_admin'].includes(currentRole)) { showMessage('Guruh yaratish uchun ruxsat yetarli emas.', true); return; }
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const status = $('#educationGroupMessage');
    const values = Object.fromEntries(new FormData(form).entries());
    button.disabled = true; status.textContent = 'Guruh saqlanmoqda…';
    try {
      const result = await api('/api/admin/education/groups', { method: 'POST', body: JSON.stringify({ name: values.name, course_id: Number(values.course_id), schedule_text: values.schedule_text || '' }) });
      form.reset();
      status.textContent = `Guruh #${Number(result.id)} yaratildi. Taklif kodi: ${result.invite_code}`;
      status.style.color = 'var(--success, #32856e)';
      await loadEducationGroups(); await loadAudit();
    } catch (error) { status.textContent = error.message; status.style.color = 'var(--danger)'; showMessage(error.message, true); }
    finally { button.disabled = false; }
  });
  $('#educationTeacherAssignForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!['ceo', 'senior_admin'].includes(currentRole)) { showMessage('Ustoz tayinlash uchun ruxsat yetarli emas.', true); return; }
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const status = $('#educationTeacherAssignMessage');
    const values = Object.fromEntries(new FormData(form).entries());
    const telegramId = String(values.telegram_id || '').trim();
    if (!/^[1-9][0-9]{4,19}$/.test(telegramId) || !Number.isSafeInteger(Number(telegramId))) { status.textContent = 'Telegram ID noto‘g‘ri.'; status.style.color = 'var(--danger)'; return; }
    button.disabled = true; status.textContent = 'Ustoz biriktirilmoqda…';
    try {
      await api('/api/admin/education/teacher-assignments', { method: 'POST', body: JSON.stringify({ telegram_id: Number(telegramId), group_id: Number(values.group_id) }) });
      form.reset(); status.textContent = 'Ustoz guruhga biriktirildi.'; status.style.color = 'var(--success, #32856e)';
      await loadEducationGroups(); await loadAudit();
    } catch (error) { status.textContent = error.message; status.style.color = 'var(--danger)'; showMessage(error.message, true); }
    finally { button.disabled = false; }
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-revoke-teacher-assignment]');
    if (!button) return;
    if (!['ceo', 'senior_admin'].includes(currentRole)) { showMessage('Bu amal uchun ruxsat yetarli emas.', true); return; }
    const id = Number(button.dataset.revokeTeacherAssignment);
    if (!window.confirm(`Ustoz tayinlovi #${id} bekor qilinsinmi?`)) return;
    button.disabled = true;
    try { await api(`/api/admin/education/teacher-assignments/${id}`, { method: 'DELETE' }); showMessage(`Tayinlov #${id} bekor qilindi.`); await loadEducationGroups(); await loadAudit(); }
    catch (error) { showMessage(error.message, true); }
    finally { button.disabled = false; }
  });

  function calendarDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('uz-UZ', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Tashkent' }).format(date);
  }
  const calendarStatusLabels = { draft: 'Qoralama', published: 'E’lon qilingan', archived: 'Arxivlangan' };
  const calendarCategoryLabels = { lesson: 'Dars', exam: 'Imtihon', holiday: 'Ta’til', event: 'Tadbir', deadline: 'Muddat', schedule_change: 'Jadval o‘zgarishi' };
  async function loadCalendar() {
    const target = $('#calendarAdminTable');
    if (!target) return;
    target.innerHTML = '<div class="empty-state">Tadbirlar yuklanmoqda…</div>';
    try {
      const data = await api('/api/admin/calendar?limit=150');
      calendarCache = Array.isArray(data.items) ? data.items : [];
      $('#calendarAdminSummary').textContent = `${Number(data.total) || calendarCache.length} ta tadbir`;
      if (!calendarCache.length) {
        target.innerHTML = '<div class="empty-state">Hozircha kalendar tadbiri yo‘q.</div>';
        return;
      }
      target.innerHTML = `<table class="data-table"><thead><tr><th>Tadbir</th><th>Turi</th><th>Sana</th><th>Guruh</th><th>Holat</th><th>Amal</th></tr></thead><tbody>${calendarCache.map(item => {
        const title = item.title_uz || item.title_en || item.title_ru || '—';
        const status = item.status || 'draft';
        const archive = status === 'archived' ? '<span class="muted">—</span>' : `<button class="button subtle compact" type="button" data-archive-calendar="${Number(item.id)}">Arxivlash</button>`;
        return `<tr><td><b>${escapeHTML(title)}</b><small>UZ / RU / EN</small></td><td>${escapeHTML(calendarCategoryLabels[item.category] || item.category)}</td><td>${escapeHTML(calendarDate(item.starts_at))}<small>${item.ends_at ? 'Tugash: ' + escapeHTML(calendarDate(item.ends_at)) : ''}</small></td><td>${item.group_name ? escapeHTML(item.group_name) : 'Barchaga ochiq'}</td><td><span class="calendar-status ${escapeHTML(status)}">${escapeHTML(calendarStatusLabels[status] || status)}</span></td><td>${archive}</td></tr>`;
      }).join('')}</tbody></table>`;
    } catch (error) {
      target.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }
  function toTashkentIso(dateValue, timeValue) {
    if (!dateValue || !timeValue) return null;
    const date = new Date(`${dateValue}T${timeValue}:00+05:00`);
    if (Number.isNaN(date.getTime())) throw new Error('Sana yoki vaqt noto‘g‘ri.');
    return date.toISOString();
  }
  $('#calendarEventForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!['ceo', 'senior_admin'].includes(currentRole)) {
      showMessage('Kalendarni boshqarish uchun CEO yoki Katta Admin ruxsati kerak.', true);
      return;
    }
    const form = event.currentTarget;
    const status = $('#calendarFormMessage');
    const button = $('#saveCalendarEvent');
    const values = Object.fromEntries(new FormData(form).entries());
    try {
      const startsAt = toTashkentIso(values.start_date, values.start_time);
      let endsAt = null;
      if (values.end_date || values.end_time) {
        if (!values.end_date || !values.end_time) throw new Error('Tugash sanasi va vaqti ikkalasi ham kiritilishi kerak.');
        endsAt = toTashkentIso(values.end_date, values.end_time);
        if (new Date(endsAt) <= new Date(startsAt)) throw new Error('Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak.');
      }
      const groupId = String(values.target_group_id || '').trim();
      if (groupId && !/^[1-9][0-9]*$/.test(groupId)) throw new Error('Guruh ID musbat butun son bo‘lishi kerak.');
      const payload = {
        titles: { uz: values.title_uz, ru: values.title_ru, en: values.title_en },
        descriptions: { uz: values.description_uz || '', ru: values.description_ru || '', en: values.description_en || '' },
        category: values.category,
        starts_at: startsAt,
        ends_at: endsAt,
        location: values.location || '',
        target_group_id: groupId ? Number(groupId) : null,
        status: values.status,
        reminder_24h: form.elements.reminder_24h.checked
      };
      button.disabled = true;
      status.textContent = 'Tadbir saqlanmoqda…';
      status.style.color = 'var(--muted)';
      const result = await api('/api/admin/calendar', { method: 'POST', body: JSON.stringify(payload) });
      form.reset();
      form.elements.reminder_24h.checked = true;
      status.textContent = `Tadbir #${Number(result.id)} saqlandi.`;
      status.style.color = 'var(--success, #32856e)';
      await loadCalendar();
      await loadAudit();
    } catch (error) {
      status.textContent = error.message || 'Tadbir saqlanmadi.';
      status.style.color = 'var(--danger)';
      showMessage(status.textContent, true);
    } finally { button.disabled = false; }
  });
  document.addEventListener('click', async (event) => {
    const archiveButton = event.target.closest('[data-archive-calendar]');
    if (!archiveButton) return;
    if (!['ceo', 'senior_admin'].includes(currentRole)) { showMessage('Bu amal uchun ruxsat yetarli emas.', true); return; }
    const id = Number(archiveButton.dataset.archiveCalendar);
    const item = calendarCache.find(row => Number(row.id) === id);
    if (!item || !window.confirm(`“${item.title_uz}” tadbirini arxivlashni tasdiqlaysizmi?`)) return;
    archiveButton.disabled = true;
    try {
      await api(`/api/admin/calendar/${id}`, { method: 'PATCH', body: JSON.stringify({
        titles: { uz: item.title_uz, ru: item.title_ru, en: item.title_en },
        descriptions: { uz: item.description_uz || '', ru: item.description_ru || '', en: item.description_en || '' },
        category: item.category,
        starts_at: item.starts_at,
        ends_at: item.ends_at || null,
        location: item.location || '',
        target_group_id: item.target_group_id || null,
        status: 'archived', reminder_24h: Boolean(item.reminder_24h)
      }) });
      showMessage(`Tadbir #${id} arxivlandi.`);
      await loadCalendar(); await loadAudit();
    } catch (error) { showMessage(error.message, true); }
    finally { archiveButton.disabled = false; }
  });
  async function loadDiagnostics() {
    const summary = $('#diagnosticsSummary');
    const grid = $('#diagnosticsGrid');
    if (!summary || !grid) return;
    summary.textContent = 'Xizmatlar holati tekshirilmoqda…';
    try {
      const data = await api('/api/admin/diagnostics');
      currentDiagnostics = data;
      const cards = [
        ['Ma’lumotlar bazasi', data.database || 'noma’lum'],
        ['Telegram bot', data.bot || 'noma’lum'],
        ['DB sxema versiyasi', `v${Number(data.schema_version) || 0}`],
        ['Muhit', data.environment || 'noma’lum'],
        ['Xabarnoma navbati', `${Number(data.application_notification_outbox?.pending) || 0} navbatda`],
        ['Yetkazish xatolari', `${Number(data.application_notification_outbox?.failed) || 0} ta`]
      ];
      grid.innerHTML = cards.map(([label, value]) => `<div class="diagnostic-card"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`).join('');
      summary.textContent = 'Himoyalangan diagnostika ma’lumotlari yangilandi.';
    } catch (error) {
      summary.textContent = 'Diagnostika ma’lumotlarini olish amalga oshmadi.';
      grid.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
    }
  }
  $('#refreshDiagnostics')?.addEventListener('click', loadDiagnostics);
  $('#refreshCalendar')?.addEventListener('click', loadCalendar);
  $('#datasetExportForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!['ceo', 'senior_admin'].includes(currentRole)) { showMessage('Eksport uchun ruxsat yetarli emas.', true); return; }
    const form = event.currentTarget;
    const button = $('#downloadDatasetExport');
    const dataset = $('#exportDataset').value;
    if (dataset === 'students' && currentRole !== 'ceo') { showMessage('O‘quvchi ma’lumotlarini faqat CEO eksport qilishi mumkin.', true); return; }
    const query = new URLSearchParams({ q: ($('#exportSearch').value || '').trim(), limit: '5000' });
    button.disabled = true;
    const previous = button.textContent;
    button.textContent = 'Tayyorlanmoqda…';
    try {
      const response = await fetch(`/api/admin/export/${encodeURIComponent(dataset)}.csv?${query.toString()}`, { credentials: 'same-origin', headers: { Accept: 'text/csv' } });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Eksport bajarilmadi (${response.status}).`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `startum-${dataset}-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1200);
      const count = response.headers.get('X-Export-Count') || '0';
      $('#exportSummary').textContent = `${count} ta yozuv eksport qilindi. ${new Date().toLocaleString('uz-UZ')}`;
      await loadAudit();
    } catch (error) {
      $('#exportSummary').textContent = error.message;
      showMessage(error.message, true);
    } finally { button.disabled = false; button.textContent = previous; }
  });

  async function loadQuizResults() {
    const target = $('#quizResultsTable');
    if (!target) return;
    target.innerHTML = '<div class="empty-state">Test natijalari yuklanmoqda…</div>';
    try {
      const data = await api('/api/admin/quiz-results?limit=200');
      const items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) {
        target.innerHTML = '<div class="empty-state">Hozircha saqlangan test natijalari yo‘q. Foydalanuvchilar botda testni yakunlaganidan keyin natijalar shu yerda ko‘rinadi.</div>';
        return;
      }
      target.innerHTML = `<table class="data-table"><thead><tr><th>Vaqt</th><th>O‘quvchi</th><th>Yo‘nalish / test</th><th>Natija</th><th>Vaqt sarfi</th><th>Manba</th></tr></thead><tbody>${items.map(item => {
        const name = [item.first_name, item.last_name].filter(Boolean).join(' ').trim() || (item.username ? '@' + item.username : `ID ${item.telegram_id}`);
        const elapsed = Math.max(0, Number(item.duration_seconds) || 0);
        const when = item.completed_at ? new Date(item.completed_at).toLocaleString('uz-UZ') : '—';
        return `<tr><td>${escapeHTML(when)}</td><td><b>${escapeHTML(name)}</b><small>${escapeHTML(item.telegram_id || '')}</small></td><td><b>${escapeHTML(item.course_name || '—')}</b><small>${escapeHTML(item.quiz_title || '—')}</small></td><td><span class="pill ${Number(item.percent) >= 80 ? '' : 'muted-pill'}">${Number(item.score)}/${Number(item.total)} · ${Number(item.percent)}%</span></td><td>${Math.floor(elapsed / 60)} daq. ${elapsed % 60} son.</td><td>${escapeHTML(item.source_chat_type || 'private')}</td></tr>`;
      }).join('')}</tbody></table>`;
    } catch (error) {
      target.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }

  const userStatusLabels = { active: 'Faol', suspended: 'STARTUM botida cheklangan' };
  const moderationActionLabels = { suspend: 'Cheklash', restore: 'Tiklash', group_mute: 'Guruhda mute', group_unmute: 'Guruhdan mute olib tashlash' };
  function formatDate(value, withTime = true) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('uz-UZ', withTime ? undefined : { dateStyle: 'medium' });
  }
  async function loadUsers() {
    const target = $('#usersTable');
    if (!target) return;
    target.innerHTML = '<div class="empty-state">Foydalanuvchilar yuklanmoqda…</div>';
    const query = new URLSearchParams({ q: ($('#userSearch')?.value || '').trim(), limit: '25', offset: String(userOffset) });
    try {
      const data = await api(`/api/admin/users?${query.toString()}`);
      const items = Array.isArray(data.items) ? data.items : [];
      $('#userSummary').textContent = `${Number(data.total) || 0} ta foydalanuvchi`;
      const pagination = $('#userPagination');
      pagination.hidden = Number(data.total) <= Number(data.limit);
      $('#userPaginationSummary').textContent = `${Number(data.total) ? userOffset + 1 : 0}–${Math.min(userOffset + items.length, Number(data.total) || 0)} / ${Number(data.total) || 0}`;
      $('#previousUsersPage').disabled = userOffset <= 0;
      $('#nextUsersPage').disabled = !data.has_more;
      if (!items.length) {
        target.innerHTML = '<div class="empty-state">Qidiruv bo‘yicha foydalanuvchi topilmadi.</div>';
        return;
      }
      target.innerHTML = `<table class="data-table"><thead><tr><th>Foydalanuvchi</th><th>Telegram ID</th><th>Ro‘yxatdan o‘tgan</th><th>Arizalar</th><th>Testlar</th><th>Holat</th><th></th></tr></thead><tbody>${items.map(item => {
        const name = [item.first_name, item.last_name].filter(Boolean).join(' ').trim() || (item.username ? `@${item.username}` : `ID ${item.telegram_id}`);
        const suspended = item.account_status === 'suspended';
        return `<tr><td><b>${escapeHTML(name)}</b><small>Ichki ID #${Number(item.id)}${item.username ? ` · @${escapeHTML(item.username)}` : ''}</small></td><td><code>${escapeHTML(item.telegram_id)}</code></td><td>${escapeHTML(formatDate(item.created_at, false))}</td><td>${Number(item.application_count) || 0}</td><td>${Number(item.quiz_attempt_count) || 0}<small>Eng yaxshi: ${Number(item.best_percent) || 0}%</small></td><td><span class="pill ${suspended ? 'muted-pill' : ''}">${userStatusLabels[item.account_status] || 'Faol'}</span></td><td><button class="button subtle compact" type="button" data-open-user="${Number(item.id)}">Ko‘rish</button></td></tr>`;
      }).join('')}</tbody></table>`;
    } catch (error) {
      target.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }
  async function loadUserDetail(userId = selectedUserId) {
    if (!userId) return;
    const detail = $('#userDetail');
    const body = $('#userDetailBody');
    detail.hidden = false;
    body.innerHTML = '<div class="empty-state">Foydalanuvchi ma’lumotlari yuklanmoqda…</div>';
    try {
      const data = await api(`/api/admin/users/${Number(userId)}`);
      const user = data.user;
      selectedUserId = Number(user.id);
      const name = [user.first_name, user.last_name].filter(Boolean).join(' ').trim() || (user.username ? `@${user.username}` : `ID ${user.telegram_id}`);
      $('#userDetailTitle').textContent = name;
      $('#userStatus').value = user.account_status === 'suspended' ? 'suspended' : 'active';
      const suspendedUntil = user.suspended_until ? ` · ${formatDate(user.suspended_until)}` : ' · muddatsiz';
      const profile = `<div class="user-facts"><div><span>Ichki ID</span><b>#${Number(user.id)}</b></div><div><span>Telegram ID</span><b>${escapeHTML(user.telegram_id)}</b></div><div><span>Username</span><b>${user.username ? '@' + escapeHTML(user.username) : '—'}</b></div><div><span>Ro‘yxatdan o‘tgan</span><b>${escapeHTML(formatDate(user.created_at))}</b></div><div><span>Holat</span><b>${escapeHTML(userStatusLabels[user.account_status] || 'Faol')}${user.account_status === 'suspended' ? escapeHTML(suspendedUntil) : ''}</b></div><div><span>Til</span><b>${escapeHTML(user.language || 'uz')}</b></div></div>`;
      const apps = data.applications || [];
      const applicationHTML = apps.length ? `<div class="user-detail-section"><h4>Arizalar (${apps.length})</h4><div class="table-wrap"><table class="data-table"><thead><tr><th>Sana</th><th>Kurs</th><th>Holat</th><th>Telefon</th><th>Manba</th></tr></thead><tbody>${apps.map(item => `<tr><td>${escapeHTML(formatDate(item.created_at))}</td><td><b>${escapeHTML(item.course_name || '—')}</b>${item.message ? `<small>${escapeHTML(item.message)}</small>` : ''}</td><td>${escapeHTML(item.status)}</td><td>${escapeHTML(item.phone || '—')}</td><td>${escapeHTML(item.source)}</td></tr>`).join('')}</tbody></table></div></div>` : '<div class="user-detail-section"><h4>Arizalar</h4><p class="muted">Bog‘langan arizalar topilmadi.</p></div>';
      const attempts = data.quiz_attempts || [];
      const quizHTML = attempts.length ? `<div class="user-detail-section"><h4>Test urinishlari (${attempts.length})</h4><div class="table-wrap"><table class="data-table"><thead><tr><th>Sana</th><th>Test</th><th>Natija</th><th>Vaqt</th></tr></thead><tbody>${attempts.map(item => `<tr><td>${escapeHTML(formatDate(item.completed_at))}</td><td><b>${escapeHTML(item.quiz_title || '—')}</b><small>${escapeHTML(item.course_name || '')}</small></td><td>${Number(item.score)}/${Number(item.total)} · ${Number(item.percent)}%</td><td>${Math.floor((Number(item.duration_seconds) || 0) / 60)} daq. ${(Number(item.duration_seconds) || 0) % 60} son.</td></tr>`).join('')}</tbody></table></div></div>` : '<div class="user-detail-section"><h4>Test natijalari</h4><p class="muted">Yakunlangan test urinishlari yo‘q.</p></div>';
      const history = data.moderation_actions || [];
      const historyHTML = history.length ? `<div class="user-detail-section"><h4>Cheklovlar tarixi (${history.length})</h4><div class="table-wrap"><table class="data-table"><thead><tr><th>Sana</th><th>Amal</th><th>Ko‘lam</th><th>Mas’ul</th><th>Sabab / muddat</th></tr></thead><tbody>${history.map(item => `<tr><td>${escapeHTML(formatDate(item.created_at))}</td><td>${escapeHTML(moderationActionLabels[item.action] || item.action)}</td><td>${escapeHTML(item.scope === 'telegram_group' ? `Telegram guruh ${item.group_chat_id || ''}` : 'STARTUM bot')}</td><td>${escapeHTML(item.actor)}</td><td>${escapeHTML(item.reason || '—')}<small>${item.expires_at ? `Tugaydi: ${escapeHTML(formatDate(item.expires_at))}` : ''}</small></td></tr>`).join('')}</tbody></table></div></div>` : '<div class="user-detail-section"><h4>Cheklovlar tarixi</h4><p class="muted">Avvalgi moderation amali yo‘q.</p></div>';
      body.innerHTML = `<div class="user-detail-sections">${profile}${applicationHTML}${quizHTML}${historyHTML}</div>`;
      $('#userDuration').value = '';
      $('#userReason').value = '';
    } catch (error) {
      body.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }

  async function loadAudit() {
    try {
      const data = await api('/api/admin/audit?limit=100');
      if (!data.items.length) { $('#auditTable').innerHTML = '<div class="empty-state">Hozircha admin amallari qayd etilmagan.</div>'; return; }
      $('#auditTable').innerHTML = `<table class="data-table"><thead><tr><th>Vaqt</th><th>Admin</th><th>Amal</th><th>Obyekt</th><th>IP</th></tr></thead><tbody>${data.items.map(item => `<tr><td>${escapeHTML(new Date(item.created_at).toLocaleString('uz-UZ'))}</td><td>${escapeHTML(item.actor)}</td><td>${escapeHTML(item.action)}<small>${escapeHTML(item.details)}</small></td><td>${escapeHTML(item.entity_type)} ${item.entity_id ? '#' + Number(item.entity_id) : ''}</td><td>${escapeHTML(item.ip_address || '—')}</td></tr>`).join('')}</tbody></table>`;
    } catch (error) { showMessage(error.message, true); }
  }
  async function loadAccounts() {
    const botTable = $('#telegramAdminsTable');
    const webTable = $('#accountsTable');
    try {
      const [botData, data] = await Promise.all([
        api('/api/admin/telegram-admins'),
        api('/api/admin/accounts')
      ]);
      const canManage = currentRole === 'ceo';
      const resetBox = $('#accountPasswordResetBox');
      if (resetBox) resetBox.hidden = !canManage;
      const resetSelect = $('#passwordResetUsername');
      if (resetSelect) {
        const previous = resetSelect.value;
        const candidates = data.items.filter(item => item.role !== 'ceo' && item.telegram_id && (item.active || item.pending_link));
        resetSelect.innerHTML = '<option value="">Hisobni tanlang</option>' + candidates.map(item => {
          const status = item.active ? 'faol' : 'nofaol';
          return `<option value="${escapeHTML(item.username)}">${escapeHTML(item.username)} · ${escapeHTML(roleLabels[item.role] || item.role)} · ${status}</option>`;
        }).join('');
        if (candidates.some(item => item.username === previous)) resetSelect.value = previous;
      }

      if (botTable) {
        if (!botData.items.length) {
          botTable.innerHTML = '<div class="empty-state">Telegram Bot administratorlari topilmadi.</div>';
        } else {
          botTable.innerHTML = `<table class="data-table"><thead><tr><th>Telegram ID</th><th>Bot roli</th><th>Bot ruxsati</th><th>Website Admin hisobi</th><th>Yaratilgan</th>${canManage ? '<th>Amal</th>' : ''}</tr></thead><tbody>${botData.items.map(item => {
            const role = String(item.role || '').toLowerCase();
            const active = Boolean(item.active);
            const invitePending = Boolean(item.bot_invite_pending);
            const isOwner = ['ceo', 'owner'].includes(role);
            const botStatus = isOwner ? 'Asosiy OWNER' : (active ? 'Faol' : (invitePending ? '/start kutilmoqda' : 'Faolsiz'));
            const webLinked = Boolean(item.web_username);
            const webActive = Boolean(item.web_active);
            const webVerified = Boolean(item.telegram_verified);
            const webStatus = !webLinked ? 'Ulanmagan' : (webActive && webVerified ? 'Faol va bog‘langan' : (webActive ? 'Birinchi kirish kutilmoqda' : 'Faolsiz'));
            const webLabel = webLinked ? `${escapeHTML(item.web_username)} · ${webStatus}` : webStatus;
            const canReissue = canManage && !isOwner && !active && !invitePending;
            const action = canReissue
              ? `<button class="button subtle compact" type="button" data-reissue-telegram-invite="${Number(item.telegram_id)}">Bot taklifini qayta berish</button>`
              : (invitePending ? '<span class="muted">/start kutilmoqda</span>' : '<span class="muted">—</span>');
            return `<tr><td><code>${escapeHTML(item.telegram_id)}</code></td><td>${escapeHTML(roleLabels[role] || role)}</td><td><span class="pill ${active || isOwner ? '' : 'muted-pill'}">${escapeHTML(botStatus)}</span></td><td>${webLabel}</td><td>${escapeHTML(item.created_at ? new Date(item.created_at).toLocaleDateString('uz-UZ') : '—')}</td>${canManage ? `<td>${action}</td>` : ''}</tr>`;
          }).join('')}</tbody></table>`;
        }
      }

      if (!data.items.length) {
        if (webTable) webTable.innerHTML = '<div class="empty-state">Website Admin hisoblari topilmadi.</div>';
      } else if (webTable) {
        webTable.innerHTML = `<table class="data-table"><thead><tr><th>Login</th><th>Telegram ID</th><th>Rol</th><th>Veb kirish</th><th>Bot holati</th><th>Yaratilgan</th>${canManage ? '<th>Amal</th>' : ''}</tr></thead><tbody>${data.items.map(item => {
          const active = Boolean(item.active);
          const self = item.username.toLowerCase() === currentUsername.toLowerCase();
          const bootstrap = Boolean(item.is_bootstrap);
          const canToggle = canManage && !self && !bootstrap && (active || Boolean(item.telegram_id));
          const botVerified = Boolean(item.telegram_verified);
          const botStatus = item.role === 'ceo' ? 'Asosiy OWNER' : (botVerified && active ? 'Faol' : (item.pending_link ? 'Bog‘lash kutilmoqda' : 'Bloklangan'));
          return `<tr><td><b>${escapeHTML(item.username)}</b>${self ? '<small>Joriy hisob</small>' : ''}</td><td>${item.telegram_id ? escapeHTML(item.telegram_id) : '<span class="muted">Bog‘lanmagan</span>'}</td><td>${escapeHTML(roleLabels[item.role] || item.role)}</td><td><span class="pill ${active ? '' : 'muted-pill'}">${active ? 'Faol' : 'Nofaol'}</span></td><td><span class="pill ${botVerified || item.role === 'ceo' ? '' : 'muted-pill'}">${escapeHTML(botStatus)}</span></td><td>${escapeHTML(item.created_at ? new Date(item.created_at).toLocaleDateString('uz-UZ') : '—')}</td>${canManage ? `<td>${canToggle ? `<button class="button subtle compact" type="button" data-account-username="${escapeHTML(item.username)}" data-account-active="${active ? '1' : '0'}">${active ? 'Faolsizlantirish' : 'Faollashtirish'}</button>` : (item.telegram_id ? '<span class="muted">—</span>' : '<span class="muted">Bot ID kerak</span>')}</td>` : ''}</tr>`;
        }).join('')}</tbody></table>`;
      }
      const openCreateButton = $('#openAdminCreateDialog');
      if (openCreateButton) openCreateButton.hidden = !canManage;
    } catch (error) {
      if (botTable) botTable.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      if (webTable) webTable.innerHTML = `<div class="empty-state">${escapeHTML(error.message)}</div>`;
      showMessage(error.message, true);
    }
  }

  async function refreshAll() {
    try { await loadStats(); await loadApplications(); if (currentView === 'users') await loadUsers(); await loadDiagnostics(); setConnected(true); showMessage('Ma’lumotlar yangilandi.'); }
    catch (error) { setConnected(false); showMessage(error.message, true); }
  }
  async function checkSession() {
    try {
      const session = await api('/api/admin/session');
      setConnected(true); showWorkspace(session); await refreshAll();
    } catch (error) {
      setConnected(error.status !== 503 ? false : true);
      showLogin(error.status === 503 ? 'Admin panel server sozlamalari bilan hali tayyor emas. Mas’ul administrator bilan bog‘laning.' : '');
    }
  }

  const passwordInput = $('#adminPasswordInput');
  const passwordToggle = $('#toggleAdminPassword');
  passwordToggle?.addEventListener('click', () => {
    if (!passwordInput) return;
    const reveal = passwordInput.type === 'password';
    passwordInput.type = reveal ? 'text' : 'password';
    passwordToggle.setAttribute('aria-pressed', String(reveal));
    passwordToggle.setAttribute('aria-label', reveal ? 'Parolni yashirish' : 'Parolni ko‘rsatish');
    passwordToggle.setAttribute('title', reveal ? 'Parolni yashirish' : 'Parolni ko‘rsatish');
  });

  $('#loginForm').addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('#loginSubmit');
    const message = $('#loginMessage');
    const data = new FormData(event.currentTarget);
    button.disabled = true; message.textContent = 'Tekshirilmoqda…';
    try {
      const session = await api('/api/admin/login', { method: 'POST', body: JSON.stringify({ username: data.get('username'), password: data.get('password') }) });
      event.currentTarget.reset(); setConnected(true); showWorkspace(session); await refreshAll();
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
  });
  $('#logoutButton').addEventListener('click', async () => {
    try { await api('/api/admin/logout', { method: 'POST', body: '{}' }); } catch (_) { /* session may already have expired */ }
    showLogin('Tizimdan chiqildi.');
  });
  $('#refreshButton').addEventListener('click', refreshAll);
  $('#refreshQuizResults')?.addEventListener('click', loadQuizResults);
  $('#sourceFilter').addEventListener('change', () => { applicationOffset = 0; loadApplications(); });

  async function submitCreateForm(form, endpoint, messageKey, successText) {
    const status = $(`[data-form-message="${messageKey}"]`);
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    status.textContent = 'Saqlanmoqda…';
    try {
      const data = Object.fromEntries(new FormData(form).entries());
      const editId = Number(form.dataset.editId || 0);
      const target = editId ? `${endpoint}/${editId}` : endpoint;
      const result = await api(target, { method: editId ? 'PATCH' : 'POST', body: JSON.stringify(data) });
      const successMessage = editId ? `${messageKey === 'course' ? 'Kurs' : 'Ustoz'} ma’lumoti yangilandi. ID: ${editId}` : `${successText} ID: ${result.id}`;
      resetEditForm(form, false);
      status.textContent = successMessage;
      status.style.color = 'var(--mint)';
      await loadCatalog(); await loadStats(); await loadAudit();
    } catch (error) {
      status.textContent = error.message;
      status.style.color = 'var(--danger)';
    } finally { submit.disabled = false; }
  }
  $('#courseForm').addEventListener('submit', event => {
    event.preventDefault();
    submitCreateForm(event.currentTarget, '/api/admin/courses', 'course', 'Kurs saqlandi.');
  });
  $('#teacherForm').addEventListener('submit', event => {
    event.preventDefault();
    submitCreateForm(event.currentTarget, '/api/admin/teachers', 'teacher', 'Ustoz saqlandi.');
  });
  $('#resourceForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = $('[data-form-message="resource"]');
    const submit = form.querySelector('button[type="submit"]');
    const data = Object.fromEntries(new FormData(form).entries());
    data.course_id = Number(data.course_id);
    submit.disabled = true;
    status.textContent = 'Saqlanmoqda…'; status.style.color = 'var(--muted)';
    try {
      const result = await api('/api/admin/resources', { method: 'POST', body: JSON.stringify(data) });
      form.reset();
      status.textContent = `Material saqlandi. ID: ${result.id}`; status.style.color = 'var(--mint)';
      await loadResources(); await loadStats(); await loadAudit();
    } catch (error) {
      status.textContent = error.message; status.style.color = 'var(--danger)';
    } finally { submit.disabled = false; }
  });
  $('#refreshResources')?.addEventListener('click', loadResources);
  $('#refreshNotifications')?.addEventListener('click', loadNotifications);
  $('#refreshMessages')?.addEventListener('click', loadMessages);
  $('#searchMessages')?.addEventListener('click', loadMessages);
  $('#messageStatusFilter')?.addEventListener('change', loadMessages);
  $('#messageSearch')?.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); loadMessages(); } });
  $('#notificationFilter')?.addEventListener('change', loadNotifications);
  $('#resourceFilter')?.addEventListener('change', loadResources);
  $('#statusFilter').addEventListener('change', () => { applicationOffset = 0; loadApplications(); });
  $('#searchApplications').addEventListener('click', () => { applicationOffset = 0; loadApplications(); });
  $('#applicationSearch').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); applicationOffset = 0; loadApplications(); } });
  $('#previousPage').addEventListener('click', () => { applicationOffset = Math.max(0, applicationOffset - 20); loadApplications(); });
  $('#nextPage').addEventListener('click', () => { applicationOffset += 20; loadApplications(); });
  $('#userSearchForm')?.addEventListener('submit', event => { event.preventDefault(); userOffset = 0; selectedUserId = 0; $('#userDetail').hidden = true; loadUsers(); });
  $('#refreshUsers')?.addEventListener('click', loadUsers);
  $('#previousUsersPage')?.addEventListener('click', () => { userOffset = Math.max(0, userOffset - 25); loadUsers(); });
  $('#nextUsersPage')?.addEventListener('click', () => { userOffset += 25; loadUsers(); });
  $('#usersTable')?.addEventListener('click', event => {
    const button = event.target.closest('[data-open-user]');
    if (!button) return;
    selectedUserId = Number(button.dataset.openUser);
    $('#userModerationMessage').textContent = '';
    loadUserDetail(selectedUserId);
  });
  $('#closeUserDetail')?.addEventListener('click', () => { selectedUserId = 0; $('#userDetail').hidden = true; });
  $('#userModerationForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!selectedUserId) return;
    const form = event.currentTarget;
    const status = $('#userModerationMessage');
    const submit = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form).entries());
    const nextStatus = values.status;
    const duration = String(values.duration_minutes || '').trim();
    const message = nextStatus === 'suspended'
      ? `Ushbu foydalanuvchining STARTUM botiga kirishini ${duration ? `${duration} daqiqaga` : 'muddatsiz'} cheklaysizmi?`
      : 'Ushbu foydalanuvchining STARTUM botiga kirishini tiklaysizmi?';
    if (!window.confirm(message)) return;
    const payload = { status: nextStatus, reason: values.reason || '' };
    if (nextStatus === 'suspended' && duration) payload.duration_minutes = Number(duration);
    submit.disabled = true;
    status.textContent = 'Holat saqlanmoqda…';
    status.style.color = 'var(--muted)';
    try {
      const result = await api(`/api/admin/users/${selectedUserId}/status`, { method: 'PATCH', body: JSON.stringify(payload) });
      await loadUserDetail(selectedUserId); await loadUsers(); await loadStats(); await loadAudit();
      status.textContent = result.status === 'suspended' ? 'STARTUM botiga kirish cheklandi.' : 'STARTUM botiga kirish tiklandi.';
      status.style.color = 'var(--mint)';
    } catch (error) {
      status.textContent = error.message;
      status.style.color = 'var(--danger)';
    } finally { submit.disabled = false; }
  });
  function setMobileSidebar(open) {
    const sidebar = $('#sidebar');
    const toggle = $('#mobileMenu');
    const backdrop = $('#sidebarBackdrop');
    if (!sidebar || !toggle) return;
    const isMobile = window.matchMedia('(max-width: 780px)').matches;
    const wasOpen = sidebar.classList.contains('open');
    const shouldOpen = Boolean(open) && isMobile;
    sidebar.classList.toggle('open', shouldOpen);
    sidebar.inert = isMobile && !shouldOpen;
    sidebar.setAttribute('aria-hidden', String(isMobile && !shouldOpen));
    document.body.classList.toggle('admin-nav-open', shouldOpen);
    toggle.setAttribute('aria-expanded', String(shouldOpen));
    toggle.setAttribute('aria-label', shouldOpen ? 'Menyuni yopish' : 'Menyuni ochish');
    if (backdrop) backdrop.hidden = !shouldOpen;
    if (shouldOpen && !wasOpen) sidebar.querySelector('[data-view]:not([hidden])')?.focus();
    if (!shouldOpen && wasOpen) toggle.focus();
  }
  $$('[data-view]').forEach(button => button.addEventListener('click', () => { setView(button.dataset.view); setMobileSidebar(false); }));
  $$('[data-goto]').forEach(button => button.addEventListener('click', () => { setView(button.dataset.goto); setMobileSidebar(false); }));
  $('#mobileMenu')?.addEventListener('click', () => setMobileSidebar(!$('#sidebar')?.classList.contains('open')));
  $('#sidebarBackdrop')?.addEventListener('click', () => setMobileSidebar(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && $('#sidebar')?.classList.contains('open')) {
      setMobileSidebar(false);
      $('#mobileMenu')?.focus();
    }
  });
  window.addEventListener('resize', () => {
    setMobileSidebar(false);
  }, { passive: true });
  setMobileSidebar(false);
  $('#selfPasswordForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = $('#selfPasswordMessage');
    const values = Object.fromEntries(new FormData(form).entries());
    if (values.new_password !== values.confirm_password) {
      status.textContent = 'Yangi parollar bir xil emas.';
      status.style.color = 'var(--danger)';
      return;
    }
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    status.textContent = 'Parol yangilanmoqda…';
    status.style.color = 'var(--muted)';
    try {
      await api('/api/admin/password/change', { method: 'POST', body: JSON.stringify({ current_password: values.current_password, new_password: values.new_password }) });
      form.reset();
      showLogin('Parol yangilandi. Xavfsizlik uchun sessiya bekor qilindi — yangi parol bilan qayta kiring.');
    } catch (error) {
      status.textContent = error.message;
      status.style.color = 'var(--danger)';
    } finally { submit.disabled = false; }
  });

  $('#accountPasswordResetForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = $('[data-form-message="password-reset"]');
    const data = Object.fromEntries(new FormData(form).entries());
    const submit = form.querySelector('button[type="submit"]');
    if (!data.username) { status.textContent = 'Avval administratorni tanlang.'; status.style.color = 'var(--danger)'; return; }
    submit.disabled = true;
    status.textContent = 'Parol yangilanmoqda…';
    status.style.color = 'var(--muted)';
    try {
      const result = await api(`/api/admin/accounts/${encodeURIComponent(data.username)}/password`, { method: 'PATCH', body: JSON.stringify({ password: data.password }) });
      status.textContent = `${result.username} paroli yangilandi. Admin yangi parol bilan saytga qayta kirishi kerak.`;
      status.style.color = 'var(--mint)';
      form.elements.password.value = '';
      await loadAccounts();
      await loadAudit();
    } catch (error) {
      status.textContent = error.message;
      status.style.color = 'var(--danger)';
    } finally { submit.disabled = false; }
  });

  const adminCreateDialog = $('#adminCreateDialog');
  const accountForm = $('#accountForm');
  const accountDetailsStep = $('#accountDetailsStep');
  const accountReviewStep = $('#accountReviewStep');
  const accountStatus = $('[data-form-message="account"]');

  function resetAdminCreateDialog() {
    accountForm?.reset();
    if (accountDetailsStep) accountDetailsStep.hidden = false;
    if (accountReviewStep) accountReviewStep.hidden = true;
    if (accountStatus) { accountStatus.textContent = ''; accountStatus.style.color = ''; }
    const confirm = $('#confirmCreateAccount');
    if (confirm) confirm.disabled = false;
  }

  $('#openAdminCreateDialog')?.addEventListener('click', () => {
    if (currentRole !== 'ceo') { showMessage('Bu amal faqat CEO uchun ruxsat etilgan.', true); return; }
    resetAdminCreateDialog();
    if (typeof adminCreateDialog?.showModal === 'function') adminCreateDialog.showModal();
    else if (adminCreateDialog) adminCreateDialog.setAttribute('open', '');
    accountForm?.elements.telegram_id?.focus();
  });

  function closeAdminCreateDialog() {
    if (adminCreateDialog?.open && typeof adminCreateDialog.close === 'function') adminCreateDialog.close();
    else adminCreateDialog?.removeAttribute('open');
  }
  $('#closeAdminCreateDialog')?.addEventListener('click', closeAdminCreateDialog);
  $('#cancelAdminCreateDialog')?.addEventListener('click', closeAdminCreateDialog);
  $('#backToAccountForm')?.addEventListener('click', () => {
    if (accountDetailsStep) accountDetailsStep.hidden = false;
    if (accountReviewStep) accountReviewStep.hidden = true;
    $('#reviewAccountButton')?.focus();
  });
  adminCreateDialog?.addEventListener('close', resetAdminCreateDialog);
  adminCreateDialog?.addEventListener('click', event => {
    if (event.target === adminCreateDialog) closeAdminCreateDialog();
  });

  $('#reviewAccountButton')?.addEventListener('click', () => {
    if (!accountForm?.reportValidity()) return;
    const values = Object.fromEntries(new FormData(accountForm).entries());
    const telegramId = String(values.telegram_id || '').trim();
    if (!/^[1-9][0-9]{4,19}$/.test(telegramId) || !Number.isSafeInteger(Number(telegramId))) {
      const field = accountForm.elements.telegram_id;
      field.setCustomValidity('Telegram ID faqat musbat raqamlar va xavfsiz butun son oralig‘ida bo‘lishi kerak.');
      field.reportValidity();
      field.addEventListener('input', () => field.setCustomValidity(''), { once: true });
      return;
    }
    $('#reviewAccountTelegram').textContent = telegramId;
    $('#reviewAccountRole').textContent = roleLabels[values.role] || values.role;
    $('#reviewAccountUsername').textContent = values.username;
    if (accountDetailsStep) accountDetailsStep.hidden = true;
    if (accountReviewStep) accountReviewStep.hidden = false;
    $('#confirmCreateAccount')?.focus();
  });

  accountForm?.addEventListener('submit', async event => {
    event.preventDefault();
    if (currentRole !== 'ceo') { showMessage('Administrator yaratish uchun CEO ruxsati kerak.', true); return; }
    if (!accountReviewStep || accountReviewStep.hidden) return;
    const form = event.currentTarget;
    const submit = $('#confirmCreateAccount');
    const data = Object.fromEntries(new FormData(form).entries());
    const telegramId = String(data.telegram_id || '').trim();
    if (!/^[1-9][0-9]{4,19}$/.test(telegramId) || !Number.isSafeInteger(Number(telegramId))) {
      if (accountStatus) { accountStatus.textContent = 'Telegram ID noto‘g‘ri.'; accountStatus.style.color = 'var(--danger)'; }
      return;
    }
    data.telegram_id = Number(telegramId);
    submit.disabled = true;
    accountStatus.textContent = 'Administrator yaratilmoqda…';
    accountStatus.style.color = 'var(--muted)';
    try {
      const result = await api('/api/admin/accounts', { method: 'POST', body: JSON.stringify(data) });
      await loadAccounts();
      await loadAudit();
      closeAdminCreateDialog();
      showMessage(`${result.username} — ${result.role_label} Website Admin hisobi yaratildi. Bot ruxsati Telegram taklifining alohida holatiga bog‘liq.`);
    } catch (error) {
      accountStatus.textContent = error.message;
      accountStatus.style.color = 'var(--danger)';
      submit.disabled = false;
    }
  });

  document.addEventListener('click', async event => {
    const retryNoticeButton = event.target.closest('[data-retry-notification]');
    if (retryNoticeButton) {
      const notificationId = Number(retryNoticeButton.dataset.retryNotification);
      retryNoticeButton.disabled = true;
      try {
        const result = await api(`/api/admin/notifications/${notificationId}/retry`, { method: 'PATCH' });
        const delivery = result.delivery || {};
        showMessage(delivery.sent ? `Xabar #${notificationId} Telegramga yuborildi.` : `Xabar #${notificationId} navbatga qaytarildi. Yetkazish holatini tekshiring.`);
        await loadNotifications(); await loadStats(); await loadAudit();
      } catch (error) { showMessage(error.message, true); }
      finally { retryNoticeButton.disabled = false; }
      return;
    }
    const editButton = event.target.closest('[data-edit-kind]');
    if (editButton) {
      beginEdit(editButton.dataset.editKind, Number(editButton.dataset.editId));
      return;
    }
    const cancelButton = event.target.closest('[data-cancel-edit]');
    if (cancelButton) {
      resetEditForm(cancelButton.closest('form'));
      return;
    }
    const catalogButton = event.target.closest('[data-toggle-kind]');
    if (catalogButton) {
      const kind = catalogButton.dataset.toggleKind;
      const plural = kind === 'course' ? 'courses' : 'teachers';
      const active = catalogButton.dataset.toggleActive !== '1';
      catalogButton.disabled = true;
      try {
        await api(`/api/admin/${plural}/${Number(catalogButton.dataset.toggleId)}/active`, { method: 'PATCH', body: JSON.stringify({ active }) });
        showMessage(`${kind === 'course' ? 'Kurs' : 'Ustoz'} holati yangilandi.`);
        await loadCatalog(); await loadStats(); await loadAudit();
      } catch (error) { showMessage(error.message, true); }
      finally { catalogButton.disabled = false; }
      return;
    }
    const resourceButton = event.target.closest('[data-toggle-resource]');
    if (resourceButton) {
      if (!['ceo', 'senior_admin'].includes(currentRole)) { showMessage('Bu amal uchun ruxsat yetarli emas.', true); return; }
      const resourceId = Number(resourceButton.dataset.toggleResource);
      const active = resourceButton.dataset.toggleActive !== '1';
      resourceButton.disabled = true;
      try {
        await api(`/api/admin/resources/${resourceId}/active`, { method: 'PATCH', body: JSON.stringify({ active }) });
        showMessage(`Material ${active ? 'faollashtirildi' : 'faolsizlantirildi'}.`);
        await loadResources(); await loadStats(); await loadAudit();
      } catch (error) { showMessage(error.message, true); }
      finally { resourceButton.disabled = false; }
      return;
    }
    const reissueInviteButton = event.target.closest('[data-reissue-telegram-invite]');
    if (reissueInviteButton) {
      if (currentRole !== 'ceo') { showMessage('Bot taklifini qayta berish faqat CEO uchun ruxsat etilgan.', true); return; }
      const telegramId = Number(reissueInviteButton.dataset.reissueTelegramInvite);
      if (!Number.isSafeInteger(telegramId) || telegramId <= 0) { showMessage('Telegram ID noto‘g‘ri.', true); return; }
      const confirmed = window.confirm(`Telegram ID ${telegramId} uchun Bot taklifini qayta berasizmi? Bog‘langan Website Admin hisobi vaqtincha o‘chiriladi va uning sessiyalari bekor qilinadi.`);
      if (!confirmed) return;
      reissueInviteButton.disabled = true;
      try {
        await api(`/api/admin/telegram-admins/${telegramId}/invite`, { method: 'POST', body: JSON.stringify({}) });
        showMessage(`${telegramId} uchun Bot taklifi qayta berildi. Foydalanuvchi botda /start yuborishi kerak.`);
        await loadAccounts(); await loadAudit();
      } catch (error) { showMessage(error.message, true); }
      finally { reissueInviteButton.disabled = false; }
      return;
    }
    const accountButton = event.target.closest('[data-account-username]');
    if (accountButton) {
      const username = accountButton.dataset.accountUsername;
      const active = accountButton.dataset.accountActive !== '1';
      accountButton.disabled = true;
      try {
        await api(`/api/admin/accounts/${encodeURIComponent(username)}/active`, { method: 'PATCH', body: JSON.stringify({ active }) });
        showMessage(`Administrator hisobi ${active ? 'faollashtirildi' : 'faolsizlantirildi'}.`);
        await loadAccounts(); await loadAudit();
      } catch (error) { showMessage(error.message, true); }
      finally { accountButton.disabled = false; }
    }
  });

  $('#exportApplications')?.addEventListener('click', exportApplications);

  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-open-application]');
    if (!button) return;
    const source = button.dataset.applicationSource;
    const id = Number(button.dataset.openApplication);
    const key = `${source}-${id}`;
    const row = document.querySelector(`[data-application-detail-row="${key}"]`);
    if (!row) return;
    row.hidden = !row.hidden;
    button.setAttribute('aria-expanded', String(!row.hidden));
    button.textContent = row.hidden ? 'To‘liq ariza' : 'Yopish';
    if (row.hidden || row.dataset.historyLoaded === 'true') return;
    const history = document.querySelector(`[data-status-history="${key}"]`);
    try {
      const data = await api(`/api/admin/applications/${source}/${id}/history`);
      const items = data.items || [];
      history.innerHTML = items.length
        ? `<b>Holat tarixi</b><ul>${items.map(item => `<li>${escapeHTML(statusLabels[item.old_status] || item.old_status)} → <b>${escapeHTML(statusLabels[item.new_status] || item.new_status)}</b> · ${escapeHTML(item.actor)} · ${escapeHTML(formatDate(item.created_at))}</li>`).join('')}</ul>`
        : '<b>Holat tarixi</b><p>Hali status o‘zgarishi bo‘lmagan.</p>';
      row.dataset.historyLoaded = 'true';
    } catch (error) {
      history.innerHTML = `<span class="error-text">${escapeHTML(error.message)}</span>`;
    }
  });

  document.addEventListener('change', async event => {
    const select = event.target.closest('[data-status-id]');
    if (!select) return;
    const original = select.value;
    select.disabled = true;
    try {
      await api(`/api/admin/applications/${select.dataset.statusSource}/${select.dataset.statusId}`, { method: 'PATCH', body: JSON.stringify({ status: original }) });
      showMessage(`Ariza #${select.dataset.statusId} holati yangilandi.`);
      await refreshAll();
    } catch (error) { showMessage(error.message, true); await loadApplications(); }
    finally { select.disabled = false; }
  });
  const themeButton = $('#adminThemeToggle');
  function applyAdminTheme(theme) {
    const next = theme === 'light' ? 'light' : 'dark';
    document.body.dataset.theme = next;
    document.documentElement.dataset.adminTheme = next;
    try { localStorage.setItem('startumAdminTheme', next); } catch (_) {}
    if (themeButton) {
      themeButton.innerHTML = next === 'light'
        ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 15.5A8.5 8.5 0 0 1 8.5 3.5a8.5 8.5 0 1 0 12 12Z"/></svg>'
        : '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></svg>';
      const themeLabel = next === 'light' ? 'Tungi rejimga o‘tish' : 'Kunduzgi rejimga o‘tish';
      themeButton.setAttribute('aria-label', themeLabel);
      themeButton.setAttribute('title', themeLabel);
      themeButton.setAttribute('aria-pressed', String(next === 'dark'));
    }
  }
  let savedAdminTheme = 'light';
  try { savedAdminTheme = localStorage.getItem('startumAdminTheme') || 'light'; } catch (_) {}
  applyAdminTheme(savedAdminTheme);
  themeButton?.addEventListener('click', () => applyAdminTheme(document.body.dataset.theme === 'light' ? 'dark' : 'light'));
  window.setInterval(() => {
    if (!currentUsername || $('#workspace').hidden) return;
    if (currentView === 'overview') { loadStats(); loadApplications(); }
    else if (currentView === 'applications') loadApplications();
    else if (currentView === 'notifications') loadNotifications();
    else if (currentView === 'calendar') loadCalendar();
  }, 30_000);
  checkSession();
})();
