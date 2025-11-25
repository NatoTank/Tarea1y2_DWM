// config.js ACTUALIZADO

const API_URL = "http://localhost:8000";

function getAuthHeaders() {
    const token = localStorage.getItem('token');
    return {
        'Content-Type': 'application/json',
        ...(token && { 'Authorization': `Bearer ${token}` })
    };
}

function logout() {
    if(confirm("¿Quieres cerrar tu sesión?")) {
        localStorage.removeItem('token');
        localStorage.removeItem('userEmail');
        localStorage.removeItem('userData');
        localStorage.removeItem('chocomaniaCart');
        window.location.href = "Home.html";
    }
}

function updateNavbarUI() {
    const token = localStorage.getItem('token');
    const loginLink = document.getElementById('loginLink'); // Buscamos por ID

    if (loginLink) {
        if (token) {
            // LOGUEADO
            loginLink.innerHTML = '<i class="fas fa-sign-out-alt" style="color: #dc3545; font-size: 1.7rem;"></i>';
            loginLink.title = "Cerrar Sesión";
            loginLink.href = "#";
            loginLink.onclick = function(e) {
                e.preventDefault();
                logout();
            };
        } else {
            // NO LOGUEADO
            loginLink.innerHTML = '<i class="fas fa-user-circle" style="color: var(--choco-primary); font-size: 1.7rem;"></i>';
            loginLink.title = "Iniciar Sesión";
            loginLink.href = "Inicio.html"; // <--- AQUÍ APUNTAMOS A INICIO.HTML
            loginLink.onclick = null;
        }
    }
}

document.addEventListener('DOMContentLoaded', updateNavbarUI);