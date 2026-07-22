const menuButton = document.getElementById("menuButton");
const navMenu = document.getElementById("navMenu");

async function readJsonResponse(response, fallbackMessage = "Request failed.") {
  let payload;
  try {
    payload = await response.json();
  } catch (_error) {
    const status = response.status ? ` (HTTP ${response.status})` : "";
    const message = response.ok ? "Server returned invalid JSON." : `${fallbackMessage}${status}`;
    throw new Error(message);
  }

  if (!response.ok) {
    const serverMessage = typeof payload?.error === "string" ? payload.error.trim() : "";
    const status = response.status ? ` (HTTP ${response.status})` : "";
    throw new Error(serverMessage || `${fallbackMessage}${status}`);
  }
  return payload;
}

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
