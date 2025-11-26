// URL de la API
const API_URL = "http://localhost:8000";

// Función para obtener headers de autenticación
function getAuthHeaders() {
    const token = localStorage.getItem('token');
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// Función para guardar token después de login
function saveToken(token) {
    localStorage.setItem('token', token);
}

// Función para verificar si está logueado
function isLoggedIn() {
    return localStorage.getItem('token') !== null;
}

// Función para logout
function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('chocomaniaCart');
    localStorage.removeItem('pendingOrder');
    window.location.href = 'Inicio.html';
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