document.addEventListener("DOMContentLoaded", function () {
    const menuIcon = document.getElementById("menu-icon");
    const navMenu = document.getElementById("nav-menu");

    if (!menuIcon || !navMenu) {
        return;
    }

    menuIcon.addEventListener("click", function (event) {
        event.stopPropagation();
        navMenu.classList.toggle("active");
    });

    navMenu.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
            navMenu.classList.remove("active");
        });
    });

    document.addEventListener("click", function (event) {
        if (!navMenu.contains(event.target) && !menuIcon.contains(event.target)) {
            navMenu.classList.remove("active");
        }
    });
});
