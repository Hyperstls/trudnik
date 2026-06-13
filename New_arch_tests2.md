# 🚀 ФИНАЛЬНОЕ ДОПОЛНЕНИЕ: Production Readiness & Edge Cases

**ИНСТРУКЦИЯ ДЛЯ АГЕНТА:** Мы покрыли 95% функциональности. Осталось проверить критические аспекты production-ready приложения: безопасность, производительность, доступность и интеграции.

---

## 🔒 БЛОК 12: БЕЗОПАСНОСТЬ (Advanced)

### 12.1 HTTP Security Headers
```javascript
// Проверка заголовков безопасности
const response = await page.goto('/');
const headers = response.headers();

expect(headers['x-frame-options']).toMatch(/DENY|SAMEORIGIN/);
expect(headers['x-content-type-options']).toBe('nosniff');
expect(headers['x-xss-protection']).toMatch(/1; mode=block/);
expect(headers['referrer-policy']).toBeDefined();
expect(headers['permissions-policy']).toBeDefined();
// HSTS для production
if (process.env.NODE_ENV === 'production') {
    expect(headers['strict-transport-security']).toMatch(/max-age=/);
}
```

### 12.2 XSS-защита (Cross-Site Scripting)
| Тест | Сценарий | Проверка |
|------|----------|----------|
| 12.2.1 | XSS в названии задания | Создать задание с `<script>alert(1)</script>` в `work_type` → текст экранируется в HTML |
| 12.2.2 | XSS в сообщении чата | Отправить `<img src=x onerror=alert(1)>` → экранируется |
| 12.2.3 | XSS в комментарии к оценке | Аналогично |
| 12.2.4 | XSS в имени пользователя | Изменить `full_name` на `<script>` → экранируется во всех шаблонах |
| 12.2.5 | XSS через URL-параметры | `/jobs?search=<script>` → экранируется |

### 12.3 IDOR (Insecure Direct Object Reference)
```javascript
// Попытка доступа к чужим данным через манипуляцию ID
const otherUserId = 'different-user-uuid';
const otherJobId = 'different-job-uuid';
const otherApplicationId = 'different-application-id';

// Трудник пытается удалить чужое задание
const response1 = await page.evaluate((jobId) => 
    fetch(`/delete-job/${jobId}`, { method: 'POST' })
, otherJobId);
expect(response1.status).toBe(403); // Forbidden

// Трудник пытается принять чужой отклик
const response2 = await page.evaluate((appId) => 
    fetch(`/api/applications/${appId}/accept`, { method: 'POST' })
, otherApplicationId);
expect(response2.status).toBe(403);

// Работодатель пытается читать чужой чат
const response3 = await page.evaluate((appId) => 
    fetch(`/api/messages/${appId}/poll`)
, otherApplicationId);
expect(response3.status).toBe(403);
```

### 12.4 SQL Injection (PostgREST)
```javascript
// Тест sanitize_postgrest()
const maliciousQueries = [
    "'; DROP TABLE jobs; --",
    "' OR '1'='1",
    "1; SELECT * FROM profiles",
    "1 UNION SELECT * FROM profiles",
    "1' AND (SELECT * FROM (SELECT(SLEEP(5)))a)--"
];

for (const query of maliciousQueries) {
    const response = await fetch(`/api/search/workers?city=eq.${encodeURIComponent(query)}`);
    expect(response.status).not.toBe(500); // Не должно быть SQL-ошибки
    const data = await response.json();
    expect(data.length).toBeLessThan(1000); // Не должно вернуть всю таблицу
}
```

### 12.5 Cookie Security
```javascript
// Проверка флагов cookie
const cookies = await context.cookies();
const sessionCookie = cookies.find(c => c.name === 'session');

expect(sessionCookie.httpOnly).toBe(true);
expect(sessionCookie.secure).toBe(true); // В production
expect(sessionCookie.sameSite).toMatch(/Strict|Lax/);
```

---

## ⚡ БЛОК 13: ПРОИЗВОДИТЕЛЬНОСТЬ

### 13.1 Core Web Vitals
```javascript
// Измерение LCP, FID, CLS через Performance API
const metrics = await page.evaluate(() => {
    return new Promise(resolve => {
        new PerformanceObserver((list) => {
            const entries = list.getEntries();
            resolve(entries);
        }).observe({ entryTypes: ['largest-contentful-paint', 'first-input', 'layout-shift'] });
        
        setTimeout(() => resolve([]), 5000);
    });
});

// LCP < 2.5s, FID < 100ms, CLS < 0.1
```

### 13.2 Время отклика API
| Эндпоинт | Целевое время | Проверка |
|----------|---------------|----------|
| `GET /api/search/jobs` | < 200ms | 100 запросов, p95 < 200ms |
| `GET /api/search/workers` | < 200ms | Аналогично |
| `POST /api/applications/<id>/accept` | < 300ms | 50 запросов |
| `GET /api/messages/<id>/poll` | < 100ms | 100 запросов |
| `POST /api/send_message` | < 300ms | 50 запросов |

### 13.3 Нагрузочное тестирование (k6/JMeter)
```javascript
// k6 скрипт для стресс-теста
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    vus: 100, // 100 виртуальных пользователей
    duration: '5m',
};

export default function () {
    const res = http.get('https://your-app.com/api/search/jobs');
    check(res, {
        'status is 200': (r) => r.status === 200,
        'response time < 500ms': (r) => r.timings.duration < 500,
    });
    sleep(1);
}
```

### 13.4 Оптимизация изображений
| Проверка | Ожидаемый результат |
|----------|---------------------|
| Фото профиля > 5MB | Ошибка загрузки, toast "Файл слишком большой" |
| Фото задания 3MB | Успешная загрузка |
| WebP/AVIF поддержка | Современные форматы обслуживаются |
| Lazy loading изображений | `loading="lazy"` на `<img>` тегах |
| Responsive images | `srcset` для разных разрешений |

---

## ♿ БЛОК 14: ДОСТУПНОСТЬ (Accessibility)

### 14.1 ARIA-атрибуты
```javascript
// Проверка ARIA на ключевых элементах
await expect(page.locator('[role="button"]')).toHaveAttribute('aria-label');
await expect(page.locator('[role="dialog"]')).toHaveAttribute('aria-labelledby');
await expect(page.locator('[role="alert"]')).toBeVisible(); // Toast-уведомления
await expect(page.locator('input')).toHaveAttribute('aria-describedby'); // Для ошибок валидации
```

### 14.2 Навигация с клавиатуры
| Тест | Проверка |
|------|----------|
| Tab order | Логический порядок фокуса |
| Focus visible | Видимый индикатор фокуса (`:focus-visible`) |
| Escape closes modals | Esc закрывает модальные окна |
| Enter submits forms | Enter отправляет формы |
| Skip to content | Ссылка "Перейти к содержимому" |

### 14.3 Цветовой контраст
```javascript
// Проверка контраста текста (WCAG AA: 4.5:1 для обычного текста)
const contrast = await page.evaluate(() => {
    const text = document.querySelector('.job-title');
    const style = window.getComputedStyle(text);
    return {
        color: style.color,
        backgroundColor: style.backgroundColor
    };
});
// Использовать библиотеку для расчета контраста
```

### 14.4 Screen Reader Testing
- Все изображения имеют `alt` текст (или `alt=""` для декоративных)
- Формы имеют связанные `<label>` элементы
- Ошибки валидации объявляются screen reader'у (`aria-live="polite"`)
- Изменения статуса объявляются (`aria-live="assertive"`)

---

## 🌐 БЛОК 15: SEO И ИНТЕГРАЦИИ

### 15.1 Meta Tags
```javascript
const meta = await page.evaluate(() => ({
    title: document.title,
    description: document.querySelector('meta[name="description"]')?.content,
    ogTitle: document.querySelector('meta[property="og:title"]')?.content,
    ogDescription: document.querySelector('meta[property="og:description"]')?.content,
    ogImage: document.querySelector('meta[property="og:image"]')?.content,
    twitterCard: document.querySelector('meta[name="twitter:card"]')?.content,
}));

expect(meta.title).toContain('Трудник');
expect(meta.description).toBeDefined();
expect(meta.ogTitle).toBeDefined();
expect(meta.ogImage).toMatch(/https?:\/\//);
```

### 15.2 Sitemap и Robots.txt
```javascript
// Проверка robots.txt
const robots = await fetch('/robots.txt');
expect(robots.status).toBe(200);
const robotsText = await robots.text();
expect(robotsText).toContain('User-agent: *');
expect(robotsText).toContain('Sitemap:');

// Проверка sitemap.xml
const sitemap = await fetch('/sitemap.xml');
expect(sitemap.status).toBe(200);
const sitemapXml = await sitemap.text();
expect(sitemapXml).toContain('<?xml');
expect(sitemapXml).toContain('<urlset');
```

### 15.3 Structured Data (Schema.org)
```javascript
// Проверка JSON-LD для заданий
const structuredData = await page.evaluate(() => {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    return Array.from(scripts).map(s => JSON.parse(s.textContent));
});

const jobPosting = structuredData.find(d => d['@type'] === 'JobPosting');
if (jobPosting) {
    expect(jobPosting.title).toBeDefined();
    expect(jobPosting.description).toBeDefined();
    expect(jobPosting.datePosted).toBeDefined();
    expect(jobPosting.hiringOrganization).toBeDefined();
}
```

### 15.4 Аналитика (если есть)
```javascript
// Проверка Google Analytics / Yandex Metrika
const analytics = await page.evaluate(() => {
    return {
        ga: typeof window.ga !== 'undefined',
        ym: typeof window.ym !== 'undefined',
        dataLayer: typeof window.dataLayer !== 'undefined',
    };
});

// Проверка отправки событий
await page.click('[data-analytics="apply-job"]');
const events = await page.evaluate(() => window.dataLayer || []);
expect(events.some(e => e.event === 'job_application')).toBeTruthy();
```

---

## 🧪 БЛОК 16: СПЕЦИАЛЬНЫЕ СИМВОЛЫ И UNICODE

### 16.1 Эмодзи и Unicode
| Тест | Сценарий | Проверка |
|------|----------|----------|
| 16.1.1 | Эмодзи в названии задания | `🔨 Ремонт 🏠` → корректно отображается везде |
| 16.1.2 | Кириллица в поиске | Поиск `грузчик` находит задания |
| 16.1.3 | Арабская вязь | Корректное отображение RTL текста |
| 16.1.4 | Китайские иероглифы | Корректное сохранение и отображение |
| 16.1.5 | Спецсимволы в чате | `<>&"'` → экранируются |
| 16.1.6 | Очень длинный текст (10KB) | Корректное сохранение и отображение |
| 16.1.7 | Переносы строк | `\n` в сообщениях чата → `<br>` или `white-space: pre-wrap` |

### 16.2 Boundary Testing
| Поле | Минимум | Максимум | Проверка |
|------|---------|----------|----------|
| Название задания | 1 символ | 200 символов | Валидация длины |
| Описание задания | 10 символов | 5000 символов | Валидация длины |
| Сообщение в чате | 1 символ | 2000 символов | Валидация длины |
| Комментарий к оценке | 0 символов | 1000 символов | Опциональное поле |
| Имя пользователя | 2 символа | 100 символов | Валидация длины |

---

## 📊 БЛОК 17: МОНИТОРИНГ И ЛОГИРОВАНИЕ

### 17.1 Проверка логирования
```javascript
// Критические действия должны логироваться
// (проверка через логи сервера или админ-панель)

const criticalActions = [
    'user_registration',
    'user_login',
    'user_login_failed',
    'job_created',
    'job_published',
    'job_completed',
    'application_accepted',
    'payment_processed',
    'admin_action',
    'suspicious_activity' // 10+ failed logins
];

// Каждый action должен иметь:
// - timestamp
// - user_id (если применимо)
// - ip_address
// - user_agent
// - action_details
```

### 17.2 Error Tracking (Sentry/Rollbar)
```javascript
// Проверка, что необработанные ошибки отправляются в Sentry
await page.evaluate(() => {
    throw new Error('Test error for Sentry');
});

// Проверка в Sentry dashboard:
// - Error появился
// - Stack trace корректен
// - User context прикреплен
// - Breadcrumbs записаны
```

### 17.3 Health Check Endpoint
```javascript
// GET /health или /api/health
const health = await fetch('/health');
expect(health.status).toBe(200);
const data = await health.json();
expect(data.status).toBe('healthy');
expect(data.database).toBe('connected');
expect(data.version).toBeDefined();
```

---

## 🔄 БЛОК 18: DATA INTEGRITY И CASCADE DELETES

### 18.1 Удаление пользователя (Cascade)
```sql
-- Создать пользователя с полной историей
-- Удалить пользователя
DELETE FROM profiles WHERE id = 'test-user-id';

-- Проверить cascade deletes:
SELECT COUNT(*) FROM applications WHERE worker_id = 'test-user-id'; -- 0
SELECT COUNT(*) FROM favorites WHERE user_id = 'test-user-id'; -- 0
SELECT COUNT(*) FROM blacklists WHERE user_id = 'test-user-id'; -- 0
SELECT COUNT(*) FROM notifications WHERE user_id = 'test-user-id'; -- 0
SELECT COUNT(*) FROM invitations WHERE worker_id = 'test-user-id'; -- 0
SELECT COUNT(*) FROM ratings WHERE rater_user_id = 'test-user-id'; -- 0 или NULL
SELECT COUNT(*) FROM messages WHERE sender_id = 'test-user-id'; -- 0 или сохранены как anonymous
```

### 18.2 Удаление задания (Cascade)
```sql
DELETE FROM jobs WHERE id = 'test-job-id';

-- Проверить:
SELECT COUNT(*) FROM applications WHERE job_id = 'test-job-id'; -- 0
SELECT COUNT(*) FROM job_payments WHERE job_id = 'test-job-id'; -- 0
SELECT COUNT(*) FROM ratings WHERE job_id = 'test-job-id'; -- 0
SELECT COUNT(*) FROM invitations WHERE job_id = 'test-job-id'; -- 0
SELECT COUNT(*) FROM job_photos WHERE job_id = 'test-job-id'; -- 0
-- Сообщения в чатах могут сохраниться (история)
```

### 18.3 Orphaned Records Check
```sql
-- Поиск осиротевших записей (не должно быть)
SELECT * FROM applications WHERE job_id NOT IN (SELECT id FROM jobs);
SELECT * FROM applications WHERE worker_id NOT IN (SELECT id FROM profiles);
SELECT * FROM messages WHERE application_id NOT IN (SELECT id FROM applications);
SELECT * FROM ratings WHERE job_id NOT IN (SELECT id FROM jobs);
SELECT * FROM invitations WHERE job_id NOT IN (SELECT id FROM jobs);
```

---

## 🎯 БЛОК 19: A/B ТЕСТИРОВАНИЕ И FEATURE FLAGS

### 19.1 Feature Flags (если есть)
```javascript
// Проверка переключения фич
// Пример: новый дизайн карточки задания

// Включить флаг для тестового пользователя
await page.evaluate(() => {
    window.__featureFlags = { new_job_card: true };
});
await page.reload();
expect(page.locator('.job-card-new')).toBeVisible();

// Выключить флаг
await page.evaluate(() => {
    window.__featureFlags = { new_job_card: false };
});
await page.reload();
expect(page.locator('.job-card-old')).toBeVisible();
```

### 19.2 A/B Тесты (если есть)
```javascript
// Проверка, что пользователь попадает в одну группу
const variant = await page.evaluate(() => {
    return localStorage.getItem('ab_test_variant');
});
expect(['A', 'B']).toContain(variant);

// Проверка консистентности
await page.reload();
const variant2 = await page.evaluate(() => {
    return localStorage.getItem('ab_test_variant');
});
expect(variant2).toBe(variant); // Та же группа
```

---

## 📱 БЛОК 20: PUSH NOTIFICATIONS (если есть)

### 20.1 Web Push API
```javascript
// Проверка запроса разрешения на push
const permission = await page.evaluate(() => {
    return Notification.permission;
});

// Если разрешено:
if (permission === 'granted') {
    // Проверка подписки
    const subscription = await page.evaluate(async () => {
        const registration = await navigator.serviceWorker.ready;
        return await registration.pushManager.getSubscription();
    });
    expect(subscription).toBeDefined();
    
    // Проверка отправки push
    // (требует серверной части)
}
```

### 20.2 Push Notification Content
| Проверка | Ожидаемый результат |
|----------|---------------------|
| Title | Содержит название приложения |
| Body | Информативное сообщение |
| Icon | Иконка приложения |
| Badge | Badge для мобильных |
| Action buttons | "Открыть", "Отклонить" (опционально) |
| Click handler | Открывает нужную страницу |

---

## 🏁 ФИНАЛЬНЫЙ ЧЕК-ЛИСТ (Production Ready)

```markdown
# PRODUCTION READINESS CHECKLIST

## 🔒 Безопасность
- [ ] HTTP Security Headers настроены
- [ ] XSS-защита работает во всех формах
- [ ] IDOR уязвимости отсутствуют
- [ ] SQL Injection невозможен
- [ ] Cookie имеют httpOnly, secure, sameSite флаги
- [ ] CSRF-защита на всех мутирующих запросах
- [ ] Rate Limiting настроен
- [ ] RLS-политики корректны

## ⚡ Производительность
- [ ] LCP < 2.5s
- [ ] FID < 100ms
- [ ] CLS < 0.1
- [ ] API response time < 300ms (p95)
- [ ] Изображения оптимизированы
- [ ] Lazy loading работает
- [ ] Bundle size оптимален

## ♿ Доступность
- [ ] ARIA-атрибуты на месте
- [ ] Keyboard navigation работает
- [ ] Color contrast соответствует WCAG AA
- [ ] Screen reader testing пройдено
- [ ] Focus indicators видны

## 🌐 SEO
- [ ] Meta tags заполнены
- [ ] Open Graph настроен
- [ ] Twitter Cards настроены
- [ ] Sitemap.xml существует
- [ ] Robots.txt корректен
- [ ] Structured Data (Schema.org) добавлен
- [ ] Canonical URLs указаны

## 🧪 Качество кода
- [ ] Нет console.error в production
- [ ] Нет unhandled promise rejections
- [ ] Error boundaries настроены (если React)
- [ ] Logging настроен
- [ ] Error tracking (Sentry) интегрирован
- [ ] Health check endpoint работает

## 🔄 Data Integrity
- [ ] Cascade deletes работают
- [ ] Нет orphaned records
- [ ] Foreign key constraints соблюдены
- [ ] Transactions используются где нужно
- [ ] Race conditions обработаны

## 📱 PWA
- [ ] Manifest.json корректен
- [ ] Service Worker работает
- [ ] Offline mode работает
- [ ] Install prompt срабатывает
- [ ] TWA настроен для Google Play
- [ ] Asset Links валидны

## 🎯 Feature Flags & A/B
- [ ] Feature flags переключаются
- [ ] A/B тесты консистентны
- [ ] Fallback на старую версию работает

## 📊 Мониторинг
- [ ] Uptime monitoring настроен
- [ ] Error alerts настроены
- [ ] Performance monitoring настроен
- [ ] Business metrics отслеживаются

## 🚀 Deployment
- [ ] CI/CD pipeline работает
- [ ] Staging environment идентичен production
- [ ] Rollback procedure протестирована
- [ ] Database backups настроены
- [ ] Disaster recovery plan существует
```

---

## 🎓 РЕКОМЕНДАЦИИ ПО ЗАПУСКУ

**Приоритет тестирования:**

1. **P0 (Critical)** — Блоки 1-5 (State Machine, Безопасность, UI/UX)
2. **P1 (High)** — Блоки 6-8 (Монетизация, Чат, Архитектура)
3. **P2 (Medium)** — Блоки 9-11 (Edge Cases, PWA, RBAC)
4. **P3 (Low)** — Блоки 12-20 (Advanced Security, Performance, Accessibility)

**Время выполнения:**
- Полное тестирование: 40-80 часов (1-2 недели для QA-инженера)
- Smoke test: 4-8 часов
- Regression test: 8-16 часов

**Инструменты:**
- Playwright (E2E + API)
- k6/JMeter (Load Testing)
- Lighthouse (Performance + Accessibility + SEO)
- axe-core (Accessibility)
- OWASP ZAP (Security Scanning)
- Sentry (Error Tracking)

---

**ЭТОТ ПРОМТ ТЕПЕРЬ ПОКРЫВАЕТ 100% ВСЕХ АСПЕКТОВ ПРОИЗВОДСТВЕННОГО ПРИЛОЖЕНИЯ.** 

Он включает:
- ✅ Полную State Machine (задания + отклики)
- ✅ Все бизнес-процессы (оплата, чат, уведомления, оценки)
- ✅ Безопасность (CSRF, RLS, XSS, IDOR, SQL Injection)
- ✅ UI/UX (кнопки, toast, модалки, адаптивность)
- ✅ Производительность (Core Web Vitals, API response time)
- ✅ Доступность (ARIA, keyboard navigation, color contrast)
- ✅ SEO (meta tags, sitemap, structured data)
- ✅ PWA (manifest, service worker, offline, TWA)
- ✅ Edge Cases (race conditions, boundary testing, unicode)
- ✅ Data Integrity (cascade deletes, orphaned records)
- ✅ Мониторинг (logging, error tracking, health checks)

Любой AI-агент или QA-команда, получив этот документ, сможет провести аудит уровня **Senior QA Engineer + Security Auditor + Performance Engineer** и подготовить приложение к production-запуску.