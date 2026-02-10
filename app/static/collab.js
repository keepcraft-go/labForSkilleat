const form = document.getElementById("contactForm");
const statusEl = document.getElementById("formStatus");

const validators = {
  fullName: (value) => value.trim().length > 0 || "이름을 입력해주세요.",
  company: (value) => value.trim().length > 0 || "회사/기관명을 입력해주세요.",
  email: (value) => {
    const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
    return ok || "이메일 형식을 확인해주세요.";
  },
  audience: (value) => value.trim().length > 0 || "대상을 입력해주세요.",
  topic: (value) => value.trim().length > 0 || "주제를 선택해주세요.",
  desiredDate: (value) => value.trim().length > 0 || "희망 일정을 선택해주세요.",
  details: (value) => value.trim().length > 0 || "문의 내용을 입력해주세요."
};

function showError(field, message) {
  const error = field.parentElement.querySelector(".collab-error");
  if (error) error.textContent = message || "";
}

function validate() {
  let ok = true;
  Object.entries(validators).forEach(([name, validator]) => {
    const field = form.elements[name];
    const result = validator(field.value);
    if (result !== true) {
      ok = false;
      showError(field, result);
    } else {
      showError(field, "");
    }
  });
  return ok;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  statusEl.textContent = "";
  if (!validate()) return;

  const payload = {
    fullName: form.fullName.value.trim(),
    company: form.company.value.trim(),
    email: form.email.value.trim(),
    phone: form.phone.value.trim(),
    audience: form.audience.value.trim(),
    topic: form.topic.value.trim(),
    desiredDate: form.desiredDate.value,
    details: form.details.value.trim()
  };

  try {
    statusEl.textContent = "전송 중...";
    const res = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || "전송 실패");
    }
    statusEl.textContent = "문의가 접수되었습니다. 곧 연락드리겠습니다.";
    form.reset();
  } catch (err) {
    statusEl.textContent = `오류: ${err.message}`;
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const desiredDate = document.getElementById("desiredDate");
  if (desiredDate) {
    const today = new Date().toISOString().slice(0, 10);
    desiredDate.value = today;
  }

  const inlineCalendarEl = document.getElementById("inlineCalendar");
  if (inlineCalendarEl && desiredDate) {
    const inlineCalendar = new FullCalendar.Calendar(inlineCalendarEl, {
      initialView: "dayGridMonth",
      height: "auto",
      initialDate: desiredDate.value,
      headerToolbar: {
        left: "prev,next",
        center: "title",
        right: ""
      },
      selectable: true,
      dateClick: (info) => {
        desiredDate.value = info.dateStr;
        inlineCalendar.select(info.dateStr);
      }
    });
    inlineCalendar.render();
    inlineCalendar.select(desiredDate.value);
  }

  const calendarEl = document.getElementById("calendar");
  if (!calendarEl) return;

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    height: "auto",
    headerToolbar: {
      left: "prev,next",
      center: "title",
      right: ""
    },
    events: "/api/schedule"
  });

  calendar.render();

  calendarEl.addEventListener("click", () => {
    window.open("/schedule", "_blank");
  });
});
