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
    const openEntryDialogs = document.querySelectorAll("[data-open-entry-dialog]");
    const closeEntryDialog = document.getElementById("close-entry-dialog");
    const entryForm = entryDialog?.querySelector("form[action='/time-tracker/entries']");
    const entryDialogTitle = document.getElementById("entry-dialog-title");
    const deleteEntryForm = document.getElementById("delete-entry-form");

    const formatMoscowCalendarDate = (date) => {
        const parts = new Intl.DateTimeFormat("en-CA", {
            timeZone: "Europe/Moscow",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hourCycle: "h23",
        }).formatToParts(date).reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
        return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
    };
    const formatCalendarDateTimeLocal = (date) => {
        const part = (number) => String(number).padStart(2, "0");
        return `${date.getUTCFullYear()}-${part(date.getUTCMonth() + 1)}-${part(date.getUTCDate())}T${part(date.getUTCHours())}:${part(date.getUTCMinutes())}`;
    };
    const formatUtcDateTimeLocal = (value) => {
        const date = new Date(`${value}:00+03:00`);
        const part = (number) => String(number).padStart(2, "0");
        return `${date.getUTCFullYear()}-${part(date.getUTCMonth() + 1)}-${part(date.getUTCDate())}T${part(date.getUTCHours())}:${part(date.getUTCMinutes())}`;
    };
    const setEntryField = (name, value) => {
        const field = entryForm?.querySelector(`[name='${name}']`);
        if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) field.value = value || "";
    };
    const openEntryForm = (start, end) => {
        if (!(entryDialog instanceof HTMLDialogElement)) return;
        if (entryForm instanceof HTMLFormElement) entryForm.action = "/time-tracker/entries";
        if (entryDialogTitle) entryDialogTitle.textContent = "Add time entry";
        const submitButton = entryForm?.querySelector("button[type='submit']");
        if (submitButton) submitButton.textContent = "Save entry";
        if (deleteEntryForm instanceof HTMLFormElement) deleteEntryForm.hidden = true;
        setEntryField("project", "");
        setEntryField("task", "");
        setEntryField("note", "");
        setEntryField("tags", "");
        setEntryField("started_at", start instanceof Date ? formatCalendarDateTimeLocal(start) : "");
        setEntryField("ended_at", end instanceof Date ? formatCalendarDateTimeLocal(end) : "");
        const endInput = entryForm?.querySelector("[name='ended_at']");
        if (endInput instanceof HTMLInputElement) endInput.required = true;
        entryDialog.showModal();
    };
    const openEditEntryForm = (event) => {
        if (!(entryDialog instanceof HTMLDialogElement) || !(entryForm instanceof HTMLFormElement)) return;
        entryForm.action = `/time-tracker/entries/${event.id}`;
        if (entryDialogTitle) entryDialogTitle.textContent = "Edit time entry";
        const submitButton = entryForm.querySelector("button[type='submit']");
        if (submitButton) submitButton.textContent = "Save changes";
        const props = event.extendedProps;
        setEntryField("project", props.project);
        setEntryField("task", props.task);
        setEntryField("note", props.note);
        setEntryField("tags", Array.isArray(props.tags) ? props.tags.join(", ") : "");
        setEntryField("started_at", formatCalendarDateTimeLocal(event.start));
        setEntryField("ended_at", event.end instanceof Date ? formatCalendarDateTimeLocal(event.end) : "");
        const endInput = entryForm.querySelector("[name='ended_at']");
        if (endInput instanceof HTMLInputElement) endInput.required = event.end instanceof Date;
        if (deleteEntryForm instanceof HTMLFormElement) {
            deleteEntryForm.action = `/time-tracker/entries/${event.id}/delete`;
            deleteEntryForm.hidden = false;
        }
        entryDialog.showModal();
    };

    openEntryDialogs.forEach((button) => button.addEventListener("click", () => openEntryForm()));
    closeEntryDialog?.addEventListener("click", () => entryDialog?.close());
    entryDialog?.addEventListener("click", (event) => {
        if (event.target === entryDialog) entryDialog.close();
    });
    entryForm?.addEventListener("submit", () => {
        ["started_at", "ended_at"].forEach((name) => {
            const input = entryForm.querySelector(`[name='${name}']`);
            if (input instanceof HTMLInputElement && input.value) input.value = formatUtcDateTimeLocal(input.value);
        });
    });

    if (calendarElement) {
        const eventData = JSON.parse(calendarElement.dataset.events || "[]");
        eventData.forEach((event) => {
            event.start = formatMoscowCalendarDate(new Date(event.start));
            if (event.end) event.end = formatMoscowCalendarDate(new Date(event.end));
        });
        const runningEventData = eventData.filter((event) =>
            event.extendedProps?.is_running || event.classNames?.includes("calendar-event-running")
        );
        const extendRunningEventData = () => {
            const now = formatMoscowCalendarDate(new Date());
            runningEventData.forEach((event) => { event.end = now; });
        };
        extendRunningEventData();
        const requestedView = calendarElement.dataset.view === "day" ? "timeGridDay" : "timeGridWeek";
        if (window.FullCalendar) {
            const calendar = new window.FullCalendar.Calendar(calendarElement, {
                initialDate: calendarElement.dataset.date,
                initialView: requestedView,
                headerToolbar: false,
                allDaySlot: false,
                selectable: true,
                selectMirror: true,
                timeZone: "UTC",
                now: () => formatMoscowCalendarDate(new Date()),
                nowIndicator: true,
                firstDay: 1,
                height: "auto",
                events: eventData,
                eventMinHeight: 26,
                eventShortHeight: 26,
                eventClick: (info) => {
                    openEditEntryForm(info.event);
                },
                select: (info) => {
                    openEntryForm(info.start, info.end);
                    calendar.unselect();
                },
            });
            calendar.render();
            const runningEvents = calendar.getEvents().filter((event) =>
                event.extendedProps.is_running || event.classNames.includes("calendar-event-running")
            );
            const extendRunningEvents = () => {
                const now = formatMoscowCalendarDate(new Date());
                runningEvents.forEach((event) => event.setEnd(now));
            };
            window.setInterval(extendRunningEvents, 60_000);
        } else {
            calendarElement.textContent = "The calendar library could not be loaded. Please refresh the page.";
        }
    }

    const reuseEntry = document.getElementById("reuse-entry");
    reuseEntry?.addEventListener("change", () => {
        const option = reuseEntry.selectedOptions[0];
        if (!option?.value) return;
        const reuseForm = reuseEntry.closest("form");
        ["project", "task", "note", "tags"].forEach((name) => {
            const field = reuseForm?.querySelector(`[name='${name}']`);
            if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
                field.value = option.dataset[name] || "";
            }
        });
    });

    const activeTimer = document.querySelector("[data-timer-start]");
    if (activeTimer instanceof HTMLElement) {
        const startedAt = new Date(activeTimer.dataset.timerStart || "");
        const todayDuration = document.querySelector("[data-today-duration]");
        const initialTodaySeconds = Number(todayDuration?.dataset.todayDuration || 0);
        const todaySyncedAt = new Date(todayDuration?.dataset.todaySyncedAt || "");
        const renderTodayDuration = () => {
            const elapsedSinceRender = Math.max(0, Math.floor((Date.now() - todaySyncedAt.getTime()) / 1000));
            const seconds = initialTodaySeconds + elapsedSinceRender;
            const totalMinutes = Math.floor(seconds / 60);
            const hours = Math.floor(totalMinutes / 60);
            const minutes = totalMinutes % 60;
            if (todayDuration instanceof HTMLElement) {
                todayDuration.textContent = `Today: ${hours ? `${hours}h ${String(minutes).padStart(2, "0")}m` : `${minutes}m`}`;
            }
        };
        const updateTimer = () => {
            const seconds = Math.max(0, Math.floor((Date.now() - startedAt.getTime()) / 1000));
            const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
            const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
            const remainingSeconds = String(seconds % 60).padStart(2, "0");
            activeTimer.textContent = `${hours}:${minutes}:${remainingSeconds}`;
            renderTodayDuration();
        };
        updateTimer();
        window.setInterval(updateTimer, 1000);
    }
})();
