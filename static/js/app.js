document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-open]").forEach((button) => {
        button.addEventListener("click", () => {
            const dialog = document.getElementById(button.dataset.open);
            if (!dialog) return;
            if (button.dataset.patient) {
                const select = dialog.querySelector("select[name='patient_id']");
                if (select) select.value = button.dataset.patient;
            }
            dialog.showModal();
            const first = dialog.querySelector("input:not([type=hidden]), select, textarea");
            if (first) first.focus();
        });
    });

    document.querySelectorAll("dialog").forEach((dialog) => {
        dialog.querySelectorAll("[data-close]").forEach((button) => {
            button.addEventListener("click", () => dialog.close());
        });
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) dialog.close();
        });
    });

    const dismiss = (toast) => {
        toast.classList.add("leaving");
        setTimeout(() => toast.remove(), 300);
    };
    document.querySelectorAll(".toast").forEach((toast, index) => {
        toast.querySelector(".toast-close").addEventListener("click", () => dismiss(toast));
        setTimeout(() => dismiss(toast), 4800 + index * 400);
    });

    const clock = document.querySelector("[data-clock]");
    if (clock) {
        const tick = () => {
            const now = new Date();
            const day = now.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
            const timeText = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            clock.textContent = `${day} · ${timeText}`;
        };
        tick();
        setInterval(tick, 1000);
    }

    const greeting = document.querySelector("[data-greeting]");
    if (greeting) {
        const hour = new Date().getHours();
        const part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
        greeting.textContent = `${part}${greeting.dataset.name ? ", " + greeting.dataset.name : ""}`;
    }

    document.querySelectorAll("[data-count]").forEach((element) => {
        const target = Number(element.dataset.count);
        const duration = 900;
        const start = performance.now();
        const step = (now) => {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            element.textContent = Math.round(target * eased).toLocaleString("en-IN");
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    });

    requestAnimationFrame(() => {
        document.querySelectorAll("[data-width]").forEach((bar) => {
            bar.style.width = `${bar.dataset.width}%`;
        });
        document.querySelectorAll("[data-ring]").forEach((ring) => {
            const target = Number(ring.dataset.ring);
            const label = ring.querySelector("b");
            const start = performance.now();
            const step = (now) => {
                const progress = Math.min((now - start) / 1000, 1);
                const value = target * (1 - Math.pow(1 - progress, 3));
                ring.style.setProperty("--value", value);
                if (label) label.textContent = `${Math.round(value)}%`;
                if (progress < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
        });
    });

    const roleSwitch = document.querySelector("[data-role-switch]");
    if (roleSwitch) {
        const label = document.querySelector("[data-username-label]");
        const input = document.getElementById("username");
        const update = () => {
            const isPatient = document.getElementById("role-patient").checked;
            label.textContent = isPatient ? "Patient ID" : "Username";
            input.placeholder = isPatient ? "e.g. PAT-1001" : "Enter admin username";
        };
        roleSwitch.addEventListener("change", update);
        update();
    }

    document.querySelectorAll("[data-toggle-pass]").forEach((button) => {
        button.addEventListener("click", () => {
            const input = button.parentElement.querySelector("input");
            input.type = input.type === "password" ? "text" : "password";
            button.classList.toggle("on");
        });
    });

    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    const billForm = document.querySelector("[data-bill-form]");
    if (billForm) {
        const output = billForm.querySelector("[data-total]");
        const formatter = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
        const recalc = () => {
            let total = 0;
            billForm.querySelectorAll("[data-amount]").forEach((input) => {
                total += parseFloat(input.value) || 0;
            });
            output.textContent = formatter.format(total);
        };
        billForm.addEventListener("input", recalc);
        recalc();
    }
});
