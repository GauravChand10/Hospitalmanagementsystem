(() => {
    const button = document.querySelector('.navbar-toggler');
    const menu = document.querySelector('#navbar');
    if (!button || !menu) return;

    button.addEventListener('click', () => {
        const open = menu.classList.toggle('show');
        button.setAttribute('aria-expanded', String(open));
    });
})();

// A login rotates Django's CSRF cookie. Use its current value so a restored
// browser page cannot submit an older embedded logout token.
document.querySelectorAll('.logout-form').forEach((form) => {
    form.addEventListener('submit', async (event) => {
        const csrfCookie = document.cookie.split('; ').find((item) => item.startsWith('csrftoken='));
        if (!csrfCookie || !window.fetch) return;

        event.preventDefault();
        const csrfToken = decodeURIComponent(csrfCookie.split('=').slice(1).join('='));
        const response = await fetch(form.action, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'X-CSRFToken': csrfToken},
            body: new FormData(form),
        });

        if (response.ok) {
            window.location.assign(response.url);
        } else if (response.status === 403) {
            window.location.reload();
        }
    });
});

window.addEventListener('pageshow', (event) => {
    if (event.persisted && document.querySelector('.logout-form')) window.location.reload();
});
