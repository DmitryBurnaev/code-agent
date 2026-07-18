(() => {
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
})();
