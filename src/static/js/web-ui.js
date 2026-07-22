(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const isMobileViewport = window.matchMedia("(max-width: 767px)").matches;
    if (isMobileViewport && !queryParams.has("view")) {
        queryParams.set("view", "day");
        window.location.replace(`${window.location.pathname}?${queryParams.toString()}`);
        return;
    }

    const sidebar = document.getElementById("sidebar");
    const sidebarOverlay = document.getElementById("sidebar-overlay");
    const sidebarOpen = document.getElementById("sidebar-open");
    const sidebarClose = document.getElementById("sidebar-close");
    const userMenu = document.getElementById("user-menu");
    const userMenuButton = document.getElementById("user-menu-button");
    const userMenuPanel = document.getElementById("user-menu-panel");

    const closeSidebar = () => {
        sidebar?.classList.remove("is-open");
        sidebarOverlay?.classList.remove("is-open");
    };
    const openSidebar = () => {
        sidebar?.classList.add("is-open");
        sidebarOverlay?.classList.add("is-open");
    };
    const closeUserMenu = () => {
        if (userMenuButton && userMenuPanel) {
            userMenuButton.setAttribute("aria-expanded", "false");
            userMenuPanel.hidden = true;
        }
    };

    sidebarOpen?.addEventListener("click", openSidebar);
    sidebarClose?.addEventListener("click", closeSidebar);
    sidebarOverlay?.addEventListener("click", closeSidebar);
    sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeSidebar));

    userMenuButton?.addEventListener("click", () => {
        if (!userMenuPanel) return;
        const isOpen = userMenuPanel.hidden === false;
        userMenuPanel.hidden = isOpen;
        userMenuButton.setAttribute("aria-expanded", String(!isOpen));
    });
    document.addEventListener("click", (event) => {
        if (userMenu && event.target instanceof Node && !userMenu.contains(event.target)) closeUserMenu();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeSidebar();
            closeUserMenu();
        }
    });

    const calendarElement = document.getElementById("time-calendar");
    const entryDialog = document.getElementById("entry-dialog");
    const openEntryDialog = document.getElementById("open-entry-dialog");
    const closeEntryDialog = document.getElementById("close-entry-dialog");
    const entryForm = entryDialog?.querySelector("form[action='/time-tracker/entries']");

    const formatDateTimeLocal = (date) => {
        const value = (part) => String(part).padStart(2, "0");
        return `${date.getFullYear()}-${value(date.getMonth() + 1)}-${value(date.getDate())}T${value(date.getHours())}:${value(date.getMinutes())}`;
    };
    const openEntryForm = (start, end) => {
        if (!(entryDialog instanceof HTMLDialogElement)) return;
        const startInput = entryForm?.querySelector("[name='started_at']");
        const endInput = entryForm?.querySelector("[name='ended_at']");
        if (startInput instanceof HTMLInputElement && start instanceof Date) startInput.value = formatDateTimeLocal(start);
        if (endInput instanceof HTMLInputElement && end instanceof Date) endInput.value = formatDateTimeLocal(end);
        entryDialog.showModal();
    };

    openEntryDialog?.addEventListener("click", () => openEntryForm());
    closeEntryDialog?.addEventListener("click", () => entryDialog?.close());
    entryDialog?.addEventListener("click", (event) => {
        if (event.target === entryDialog) entryDialog.close();
    });

    if (calendarElement) {
        const eventData = JSON.parse(calendarElement.dataset.events || "[]");
        const requestedView = calendarElement.dataset.view === "day" ? "timeGridDay" : "timeGridWeek";
        if (window.FullCalendar) {
            const calendar = new window.FullCalendar.Calendar(calendarElement, {
                initialDate: calendarElement.dataset.date,
                initialView: requestedView,
                headerToolbar: false,
                allDaySlot: false,
                selectable: true,
                selectMirror: true,
                nowIndicator: true,
                firstDay: 1,
                height: "auto",
                events: eventData,
                eventClick: (info) => {
                    const entry = document.querySelector(`[data-entry-id='${info.event.id}']`);
                    entry?.setAttribute("open", "");
                    entry?.scrollIntoView({ behavior: "smooth", block: "center" });
                },
                select: (info) => {
                    openEntryForm(info.start, info.end);
                    calendar.unselect();
                },
            });
            calendar.render();
        } else {
            calendarElement.textContent = "The calendar library could not be loaded. Please refresh the page.";
        }
    }

    const reuseEntry = document.getElementById("reuse-entry");
    reuseEntry?.addEventListener("change", () => {
        const option = reuseEntry.selectedOptions[0];
        if (!option?.value) return;
        document.querySelectorAll("form[action='/time-tracker/timer/start'], form[action='/time-tracker/entries']")
            .forEach((form) => {
                ["project", "task", "note", "tags"].forEach((name) => {
                    const field = form.querySelector(`[name='${name}']`);
                    if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
                        field.value = option.dataset[name] || "";
                    }
                });
            });
    });

    const activeTimer = document.querySelector("[data-timer-start]");
    if (activeTimer instanceof HTMLElement) {
        const startedAt = new Date(activeTimer.dataset.timerStart || "");
        const updateTimer = () => {
            const seconds = Math.max(0, Math.floor((Date.now() - startedAt.getTime()) / 1000));
            const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
            const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
            const remainingSeconds = String(seconds % 60).padStart(2, "0");
            activeTimer.textContent = `${hours}:${minutes}:${remainingSeconds}`;
        };
        updateTimer();
        window.setInterval(updateTimer, 1000);
    }
})();
