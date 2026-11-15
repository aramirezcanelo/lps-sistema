(() => {
  let activeModal = null;
  let lastTrigger = null;
  let pendingDelete = null;
  let pendingConfirmForm = null;
  const confirmedForms = new WeakSet();
  let lastDialogTrigger = null;

  // Cierra el diálogo activo y devuelve el foco al control que lo abrió.
  function closeModal() {
    if (!activeModal) return;
    activeModal.classList.remove("show");
    activeModal.style.display = "none";
    activeModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    document.querySelector(".modal-backdrop")?.remove();
    activeModal = null;
    lastTrigger?.focus();
  }

  // Marca o desmarca los registros que pertenecen a una acción masiva.
  document.addEventListener("change", (event) => {
    const master = event.target.closest("[data-select-all]");
    if (!master) return;

    const formId = master.dataset.selectAll;
    const items = document.querySelectorAll(`input[type="checkbox"][form="${formId}"][name="ids"]`);
    items.forEach((item) => { item.checked = master.checked; });
  });

  // Duplica o quita renglones de productos dentro de una compra o venta.
  document.addEventListener("click", (event) => {
    const add = event.target.closest("[data-add-item]");
    const remove = event.target.closest("[data-remove-item]");
    if (!add && !remove) return;
    const form = event.target.closest("form[data-line-items]");
    const list = form?.querySelector("[data-item-list]");
    if (!list) return;
    if (add) {
      const row = list.querySelector(".finance-line-item")?.cloneNode(true);
      if (!row) return;
      row.querySelectorAll("input").forEach((input) => { input.value = input.name === "productos_cantidad" ? "1" : ""; });
      list.append(row);
      row.querySelector("input")?.focus();
    } else {
      if (list.querySelectorAll(".finance-line-item").length === 1) {
        showNotice("Cada registro debe conservar al menos un producto.");
        return;
      }
      remove.closest(".finance-line-item")?.remove();
    }
    const rows = list.querySelectorAll(".finance-line-item");
    list.querySelectorAll("[data-remove-item]").forEach((button) => { button.disabled = rows.length === 1; });
  });

  // Actualiza el control general cuando el usuario cambia una selección individual.
  document.addEventListener("change", (event) => {
    const item = event.target.closest('input[type="checkbox"][name="ids"][form]');
    if (!item) return;

    const master = document.querySelector(`[data-select-all="${item.getAttribute("form")}"]`);
    if (!master) return;

    const items = document.querySelectorAll(`input[type="checkbox"][form="${item.getAttribute("form")}"][name="ids"]`);
    const checkedItems = Array.from(items).filter((checkbox) => checkbox.checked);
    master.checked = items.length > 0 && checkedItems.length === items.length;
    master.indeterminate = checkedItems.length > 0 && checkedItems.length < items.length;
  });

  // Abre un diálogo integrado para confirmar acciones de eliminación.
  function openConfirmDialog(form, message, submitter) {
    const dialog = document.getElementById("app-confirm-dialog");
    if (!dialog) return false;

    pendingConfirmForm = { form, submitter };
    lastDialogTrigger = document.activeElement;
    const copy = dialog.querySelector("#app-confirm-message");
    if (copy) copy.textContent = `${message}. ¿Quieres continuar?`;
    dialog.classList.add("is-open");
    dialog.setAttribute("aria-hidden", "false");
    document.body.classList.add("dialog-open");
    dialog.querySelector("[data-dialog-cancel]")?.focus();
    return true;
  }

  // Cierra el diálogo sin enviar el formulario que estaba pendiente.
  function closeConfirmDialog() {
    const dialog = document.getElementById("app-confirm-dialog");
    if (!dialog) return;

    dialog.classList.remove("is-open");
    dialog.setAttribute("aria-hidden", "true");
    document.body.classList.remove("dialog-open");
    pendingConfirmForm = null;
    lastDialogTrigger?.focus();
  }

  // Intercepta el envío de acciones masivas para evitar los cuadros nativos.
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form");
    if (!form) return;
    if (confirmedForms.has(form)) { confirmedForms.delete(form); return; }
    const submitter = event.submitter || null;
    const message = submitter?.dataset.confirmAction || form.dataset.confirmAction;
    if (!message) return;

    const selected = form.querySelectorAll('input[name="ids"]:checked');
    const isBulkAction = form.classList.contains("bulk-actions");
    if (isBulkAction && selected.length === 0 && !form.querySelector('input[name="id"]')) {
      event.preventDefault();
      showNotice("Selecciona al menos un elemento antes de continuar.");
      return;
    }

    event.preventDefault();
    openConfirmDialog(form, message, submitter);
  });

  // Confirma o cancela la acción desde el diálogo personalizado.
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-dialog-cancel], [data-dialog-close]")) {
      closeConfirmDialog();
      return;
    }

    if (event.target.closest("[data-dialog-confirm]")) {
      const pending = pendingConfirmForm;
      closeConfirmDialog();
      if (pending?.form) {
        const { form, submitter } = pending;
        if (form.classList.contains("bulk-actions") && !form.querySelector('input[name="id"]') && form.querySelectorAll('input[name="ids"]:checked').length === 0) {
          showNotice("Selecciona al menos un elemento antes de continuar.");
          return;
        }
        if (form.dataset.confirming === "true") return;
        form.dataset.confirming = "true";
        confirmedForms.add(form);
        if (typeof form.requestSubmit === "function") form.requestSubmit(submitter || undefined);
        else form.submit();
        window.setTimeout(() => { delete form.dataset.confirming; }, 0);
      }
      return;
    }
  });

  // Mensajes breves integrados para indicar validaciones que el usuario debe corregir.
  function showNotice(message) {
    let notice = document.querySelector(".app-notice");
    if (!notice) {
      notice = document.createElement("div");
      notice.className = "app-notice";
      notice.setAttribute("role", "status");
      notice.setAttribute("aria-live", "polite");
      document.body.append(notice);
    }
    notice.textContent = message;
    notice.classList.add("is-visible");
    window.clearTimeout(notice.hideTimer);
    notice.hideTimer = window.setTimeout(() => notice.classList.remove("is-visible"), 4200);
  }

  // Los controles de vuelta siguen el historial, incluidos los gestos nativos del móvil.
  document.addEventListener("click", (event) => {
    const backButton = event.target.closest("[data-go-back]");
    if (!backButton) return;

    const fallback = backButton.dataset.fallback || "/";
    if (window.history.length > 1 && document.referrer && new URL(document.referrer).origin === window.location.origin) {
      window.history.back();
    } else {
      window.location.assign(fallback);
    }
  });

  // Añade destinos seguros al historial para que volver funcione al abrir enlaces directos.
  if (window.history.state?.lpsView !== window.location.pathname) {
    window.history.replaceState({ ...(window.history.state || {}), lpsView: window.location.pathname }, "", window.location.href);
  }

  // Permite volver mediante un gesto de borde lateral en dispositivos táctiles.
  let touchStartX = null;
  let touchStartY = null;
  document.addEventListener("touchstart", (event) => {
    if (event.touches.length !== 1) return;
    touchStartX = event.touches[0].clientX;
    touchStartY = event.touches[0].clientY;
  }, { passive: true });
  document.addEventListener("touchend", (event) => {
    if (touchStartX === null || touchStartY === null || event.changedTouches.length !== 1) return;
    const deltaX = event.changedTouches[0].clientX - touchStartX;
    const deltaY = Math.abs(event.changedTouches[0].clientY - touchStartY);
    const beganAtLeftEdge = touchStartX < 24;
    touchStartX = null;
    touchStartY = null;
    if (beganAtLeftEdge && deltaX > 90 && deltaY < 60 && !document.body.classList.contains("dialog-open")) {
      if (window.history.length > 1 && document.referrer && new URL(document.referrer).origin === window.location.origin) window.history.back();
      else window.location.assign("/");
    }
  }, { passive: true });

  // Centraliza las interacciones pequeñas del menú, diálogos y confirmaciones.
  document.addEventListener("click", (event) => {
    const menuTrigger = event.target.closest("[data-menu-toggle]");
    if (menuTrigger) {
      const menu = document.getElementById(menuTrigger.getAttribute("aria-controls"));
      if (menu) {
        const open = menu.classList.toggle("is-open");
        menuTrigger.setAttribute("aria-expanded", String(open));
        menuTrigger.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
      }
      return;
    }

    const confirmDelete = event.target.closest("[data-confirm-delete-submit]");
    if (confirmDelete) {
      event.preventDefault();
      const pending = pendingDelete;
      pendingDelete = null;
      closeModal();
      if (pending?.form && pending?.button) pending.form.requestSubmit(pending.button);
      return;
    }

    const deleteTrigger = event.target.closest("[data-confirm-delete]");
    if (deleteTrigger) {
      pendingDelete = { form: deleteTrigger.form, button: deleteTrigger };
      const name = document.querySelector("[data-confirm-account]");
      if (name) name.textContent = deleteTrigger.dataset.accountName || "esta cuenta";
    }

    const trigger = event.target.closest('[data-bs-toggle="modal"]');
    if (trigger) {
      const selector = trigger.getAttribute("data-bs-target");
      const modal = selector ? document.querySelector(selector) : null;
      if (modal) {
        event.preventDefault();
        activeModal = modal;
        lastTrigger = trigger;
        modal.style.display = "block";
        modal.setAttribute("aria-hidden", "false");
        modal.classList.add("show");
        document.body.classList.add("modal-open");
        const backdrop = document.createElement("div");
        backdrop.className = "modal-backdrop fade show";
        backdrop.addEventListener("click", closeModal, { once: true });
        document.body.append(backdrop);
        modal.querySelector("input, select, textarea, button")?.focus();
      }
      return;
    }

    if (event.target.closest('[data-bs-dismiss="modal"]')) {
      event.preventDefault();
      closeModal();
      return;
    }

    const collapseTrigger = event.target.closest('[data-bs-toggle="collapse"]');
    if (collapseTrigger) {
      const selector = collapseTrigger.getAttribute("data-bs-target");
      const target = selector ? document.querySelector(selector) : null;
      if (target) {
        event.preventDefault();
        const expanded = target.classList.toggle("show");
        collapseTrigger.setAttribute("aria-expanded", String(expanded));
      }
    }

    if (event.target.classList.contains("modal") && event.target === activeModal) closeModal();
  });

  // Permite cerrar un diálogo con Escape para mejorar la accesibilidad.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { closeModal(); closeConfirmDialog(); }
  });

  // Marca como activa la vista que corresponde a la dirección actual.
  const currentPath = window.location.pathname.replace(/\/$/, "") || "/";
  document.querySelectorAll(".site-nav .nav-link[href]").forEach((link) => {
    const linkPath = new URL(link.href, window.location.origin).pathname.replace(/\/$/, "") || "/";
    if (linkPath === currentPath) {
      link.classList.add("active");
      link.setAttribute("aria-current", "page");
    }
  });

  // Muestra los nombres elegidos en el control de carga múltiple con estilo propio.
  document.querySelectorAll("[data-file-picker]").forEach((input) => {
    input.addEventListener("change", () => {
      const output = document.querySelector(input.dataset.filePickerName || "[data-file-picker-name]");
      if (!output) return;
      const files = Array.from(input.files || []);
      output.textContent = files.length ? `${files.length} archivo${files.length === 1 ? "" : "s"} seleccionado${files.length === 1 ? "" : "s"}` : "Ningún archivo seleccionado";
      output.title = files.map((file) => file.name).join("\n");
    });
  });

  // Abre el selector de reemplazo y envía el formulario tras elegir un archivo.
  document.querySelectorAll("[data-replace-file]").forEach((input) => {
    input.addEventListener("change", () => {
      const form = input.form;
      if (!form || !input.files?.length) return;
      const label = form.querySelector("[data-replace-name]");
      if (label) label.textContent = input.files[0].name;
      form.requestSubmit();
    });
  });
})();
