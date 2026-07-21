const menuButton = document.getElementById("menuButton");
const navMenu = document.getElementById("navMenu");

if (menuButton && navMenu) {
  const currentPath = window.location.pathname === "/" ? "/" : window.location.pathname;
  for (const link of navMenu.querySelectorAll("a")) {
    const linkPath = new URL(link.href).pathname;
    if (linkPath === currentPath) {
      link.classList.add("active");
    }
  }

  menuButton.addEventListener("click", () => {
    const open = navMenu.classList.toggle("open");
    menuButton.setAttribute("aria-expanded", open ? "true" : "false");
  });

  document.addEventListener("click", (event) => {
    if (event.target === menuButton || navMenu.contains(event.target)) return;
    navMenu.classList.remove("open");
    menuButton.setAttribute("aria-expanded", "false");
  });
}
