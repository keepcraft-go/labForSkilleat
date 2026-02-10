require("dotenv").config();
const express = require("express");
const path = require("path");
const nodemailer = require("nodemailer");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(__dirname));

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST,
  port: Number(process.env.SMTP_PORT || 587),
  secure: process.env.SMTP_SECURE === "true",
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS
  }
});

app.post("/api/contact", async (req, res) => {
  const {
    fullName,
    company,
    email,
    phone,
    audience,
    topic,
    desiredDate,
    details
  } = req.body || {};

  if (!fullName || !company || !email || !audience || !topic || !desiredDate || !details) {
    return res.status(400).json({ message: "필수 항목이 누락되었습니다." });
  }

  const subject = `[협업 문의] ${fullName} - ${topic}`;
  const text = `
이름: ${fullName}
회사/기관: ${company}
이메일: ${email}
연락처: ${phone || "-"}
대상: ${audience}
주제: ${topic}
희망 일정: ${desiredDate}

문의 내용:
${details}
  `.trim();

  try {
    await transporter.sendMail({
      from: process.env.MAIL_FROM,
      to: "contact@skilleat.com",
      subject,
      text
    });
    return res.json({ ok: true });
  } catch (err) {
    return res.status(500).json({ message: "메일 전송 실패" });
  }
});

// Placeholder events. Replace with DB-backed events if needed.
app.get("/api/schedule", (_req, res) => {
  res.json([
    {
      title: "협업 가능",
      start: new Date().toISOString().slice(0, 10),
      allDay: true
    }
  ]);
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
