/* No npm dependencies: run with node tests/frontend.test.cjs. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup(respond) {
    const storage = new Map();
    const calls = [];
    const events = [];
    const context = vm.createContext({
        URL, Event, AbortController, setTimeout, clearTimeout,
        window: { location: { origin: "http://localhost:8000" } },
        sessionStorage: {
            getItem: key => storage.get(key) || null,
            setItem: (key, value) => storage.set(key, value),
            removeItem: key => storage.delete(key),
        },
        document: { dispatchEvent: event => events.push(event.type) },
        fetch: async (url, options) => {
            calls.push({ url, options });
            const result = await respond(url, options);
            return {
                status: result.status,
                ok: result.status >= 200 && result.status < 300,
                json: async () => result.body,
            };
        },
    });
    vm.runInContext(fs.readFileSync("static/frontend/api.js", "utf8"), context);
    const api = vm.runInContext("api", context);
    return { api, storage, calls, events };
}

function tokenFrom(options) {
    return options.headers.Authorization;
}

test("loads every DRF page", async () => {
    const session = setup(async url => ({
        status: 200,
        body: url.includes("page=2")
            ? { results: [{ id: 2 }], next: null }
            : { results: [{ id: 1 }], next: "http://localhost:8000/api/v1/courses/?page=2" },
    }));
    const items = await session.api.getAll("/api/v1/courses/");
    assert.equal(items.length, 2);
    assert.equal(items[1].id, 2);
});

test("rejects cross-origin pagination without leaking a token", async () => {
    const session = setup(async () => ({
        status: 200, body: { results: [], next: "https://example.com/api/v1/courses/" },
    }));
    session.api.saveTokens({ access: "demo-access", refresh: "demo-refresh" });
    await assert.rejects(session.api.getAll("/api/v1/courses/"), /unexpected API address/);
    assert.equal(session.calls.length, 1);
});

test("detects repeated pagination", async () => {
    const session = setup(async () => ({
        status: 200, body: { results: [], next: "/api/v1/courses/" },
    }));
    await assert.rejects(session.api.getAll("/api/v1/courses/"), /repeated page/);
});

test("concurrent expired requests share one refresh and retry with new JWT", async () => {
    const session = setup(async (url, options) => {
        if (url.includes("token/refresh")) {
            await new Promise(resolve => setTimeout(resolve, 5));
            return { status: 200, body: { access: "new-access" } };
        }
        return tokenFrom(options) === "Bearer new-access"
            ? { status: 200, body: { total_xp: 10 } }
            : { status: 401, body: { detail: "Expired" } };
    });
    session.api.saveTokens({ access: "old-access", refresh: "demo-refresh" });
    const results = await Promise.all([
        session.api.request("/api/v1/me/"),
        session.api.request("/api/v1/me/progress/"),
    ]);
    assert.equal(results[0].total_xp, 10);
    assert.equal(results[1].total_xp, 10);
    assert.equal(session.calls.filter(call => call.url.includes("token/refresh")).length, 1);
});

test("invalid refresh clears the session and notifies the UI", async () => {
    const session = setup(async () => ({ status: 401, body: { detail: "Expired" } }));
    session.api.saveTokens({ access: "old-access", refresh: "old-refresh" });
    await assert.rejects(session.api.request("/api/v1/me/"), /session has expired/);
    assert.equal(session.api.hasSession(), false);
    assert.deepEqual(session.events, ["auth:expired"]);
});

test("a late refresh cannot undo logout", async () => {
    let resolveRefresh;
    let refreshStarted;
    const started = new Promise(resolve => { refreshStarted = resolve; });
    const session = setup(async url => {
        if (url.includes("token/refresh")) {
            refreshStarted();
            return new Promise(resolve => { resolveRefresh = resolve; });
        }
        return { status: 401, body: {} };
    });
    session.api.saveTokens({ access: "old-access", refresh: "old-refresh" });
    const request = session.api.request("/api/v1/me/");
    await started;
    session.api.clearTokens();
    resolveRefresh({ status: 200, body: { access: "late-access" } });
    await assert.rejects(request, /session changed/);
    assert.equal(session.api.hasSession(), false);
    assert.equal(session.storage.has("linguaquest.access"), false);
});

test("refresh service errors preserve tokens for a later attempt", async () => {
    const session = setup(async url => ({
        status: url.includes("token/refresh") ? 503 : 401, body: {},
    }));
    session.api.saveTokens({ access: "old-access", refresh: "demo-refresh" });
    await assert.rejects(session.api.request("/api/v1/me/"), /couldn’t renew/);
    assert.equal(session.api.hasSession(), true);
});

test("a late retried 401 cannot log out a newly signed-in account", async () => {
    let resolveRetry;
    let retryStarted;
    const started = new Promise(resolve => { retryStarted = resolve; });
    const session = setup(async (url, options) => {
        if (url.includes("token/refresh")) {
            return { status: 200, body: { access: "renewed-access" } };
        }
        if (tokenFrom(options) === "Bearer renewed-access") {
            retryStarted();
            return new Promise(resolve => { resolveRetry = resolve; });
        }
        return { status: 401, body: {} };
    });
    session.api.saveTokens({ access: "old-access", refresh: "old-refresh" });
    const request = session.api.request("/api/v1/me/");
    await started;
    session.api.clearTokens();
    session.api.saveTokens({ access: "other-access", refresh: "other-refresh" });
    resolveRetry({ status: 401, body: {} });
    await assert.rejects(request, /session changed/);
    assert.equal(session.storage.get("linguaquest.access"), "other-access");
    assert.equal(session.storage.get("linguaquest.refresh"), "other-refresh");
    assert.deepEqual(session.events, []);
});

test("validation errors are readable and do not repeat a submission", async () => {
    const session = setup(async () => ({ status: 400, body: { answer: ["Choose an option."] } }));
    await assert.rejects(session.api.request("/api/v1/exercises/12/submit/", {
        method: "POST", body: { answer: "invalid" },
    }), /answer: Choose an option/);
    assert.equal(session.calls.length, 1);
});

test("login never attaches an existing access token", async () => {
    const session = setup(async () => ({ status: 401, body: { detail: "Invalid credentials." } }));
    session.api.saveTokens({ access: "old-access", refresh: "old-refresh" });
    await assert.rejects(session.api.request("/api/v1/auth/token/", {
        method: "POST", authenticated: false,
        body: { username: "student", password: "not-stored" },
    }), /Invalid credentials/);
    assert.equal(tokenFrom(session.calls[0].options), undefined);
    assert.equal(session.calls.length, 1);
    assert.equal(session.storage.size, 2);
});

/* Minimal DOM doubles test UI state, not browser rendering or layout. */
function setupUI(overrides = {}) {
    const nodes = new Map();
    const timers = new Map();
    let timerId = 0;
    function node(id = "") {
        return {
            id, hidden: false, disabled: false, textContent: "", value: "", dataset: {},
            children: [], classList: { toggle() {}, add() {} },
            addEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {}, reset() {},
            append(...items) { this.children.push(...items); },
            replaceChildren() { this.children = []; },
        };
    }
    function find(selector) {
        if (selector === "#answer-inputs input:checked") {
            return null;
        }
        if (!nodes.has(selector)) {
            nodes.set(selector, node(selector.slice(1)));
        }
        return nodes.get(selector);
    }
    const progress = {
        total_xp: 0, completed_exercise_ids: [], completed_lesson_ids: [],
        completed_exercise_count: 0, completed_lesson_count: 0,
    };
    const context = vm.createContext({
        document: {
            querySelector: find,
            querySelectorAll: selector => selector === ".view"
                ? ["dashboard", "courses", "lessons", "exercise", "profile"].map(page => find("#" + page + "-view"))
                : [],
            createElement: () => node(),
            addEventListener() {},
        },
        window: { addEventListener() {} },
        setTimeout: callback => { timers.set(++timerId, callback); return timerId; },
        clearTimeout: id => timers.delete(id),
        api: {
            hasSession: () => false,
            clearTokens() {},
            request: async () => progress,
            getAll: async () => [{ id: 17, kind: "text", prompt: "Your answer?", xp_reward: 10 }],
            ...overrides,
        },
    });
    vm.runInContext(fs.readFileSync("static/frontend/app.js", "utf8"), context);
    const state = vm.runInContext("state", context);
    state.user = { username: "student" };
    state.progress = progress;
    state.lesson = { id: 8, title: "Practice" };
    return { context, state, find, timers };
}

test("opening a lesson reveals its inputs and clears the loading state", async () => {
    const ui = setupUI();
    await ui.context.openLesson(ui.state.lesson);
    assert.equal(ui.find("#page-loading").hidden, true);
    assert.equal(ui.find("#exercise-view").hidden, false);
    assert.equal(ui.find("#exercise-card").hidden, false);
    assert.equal(ui.find("#exercise-prompt").textContent, "Your answer?");
    assert.equal(ui.find("#answer-inputs").children.length, 3);
});

test("empty lessons show an honest empty summary", async () => {
    const ui = setupUI({ getAll: async () => [] });
    await ui.context.openLesson(ui.state.lesson);
    assert.equal(ui.find("#lesson-summary").hidden, false);
    assert.equal(ui.find("#exercise-card").hidden, true);
    assert.match(ui.find("#lesson-summary-text").textContent, /no exercises/);
});

test("pending and retrying feedback schedule polling and show the mock label", async () => {
    const ui = setupUI();
    await ui.context.openLesson(ui.state.lesson);
    const version = vm.runInContext("viewVersion", ui.context);
    for (const status of ["pending", "processing", "retrying"]) {
        await ui.context.displaySubmission({ id: 1, status, provider: "mock" }, version);
        assert.equal(ui.find("#mock-notice").hidden, false);
        assert.equal(ui.find("#exercise-actions").hidden, true);
        assert.equal(ui.timers.size, 1);
    }
    ui.context.showAuth();
    assert.equal(ui.timers.size, 0);
});

test("completed feedback waits for refreshed progress before enabling Next", async () => {
    const ui = setupUI();
    await ui.context.openLesson(ui.state.lesson);
    let resolveProgress;
    ui.context.api.request = () => new Promise(resolve => { resolveProgress = resolve; });
    const version = vm.runInContext("viewVersion", ui.context);
    const completion = ui.context.displaySubmission({
        id: 1, status: "completed", provider: "mock", is_correct: true, xp_awarded: 10,
        feedback: { score: 80, corrections: ["Use present simple."], explanation: "Mock result." },
    }, version);
    assert.equal(ui.find("#exercise-actions").hidden, true);
    resolveProgress({
        total_xp: 10, completed_exercise_ids: [17], completed_lesson_ids: [8],
        completed_exercise_count: 1, completed_lesson_count: 1,
    });
    await completion;
    assert.equal(ui.find("#exercise-actions").hidden, false);
    assert.equal(ui.find("#feedback-score").textContent, "Writing score: 80 / 100");
    assert.equal(ui.find("#lesson-progress-bar").value, 100);
    ui.state.exerciseIndex += 1;
    ui.context.renderExercise();
    assert.equal(ui.find("#lesson-summary-title").textContent, "A lesson well learned.");
});

test("failed and unavailable feedback retain an explicit explanation", async () => {
    const ui = setupUI();
    await ui.context.openLesson(ui.state.lesson);
    const version = vm.runInContext("viewVersion", ui.context);
    for (const status of ["failed", "unavailable"]) {
        await ui.context.displaySubmission({
            id: 1, status, provider: "disabled", error_code: "ai_not_configured", xp_awarded: 0,
        }, version);
        assert.match(ui.find("#result-message").textContent, /no evaluation or XP/);
        assert.equal(ui.find("#feedback-details").hidden, true);
        assert.equal(ui.find("#exercise-actions").hidden, false);
    }
});

test("whitespace answers are rejected without submitting a request", async () => {
    let submitted = false;
    const ui = setupUI();
    await ui.context.openLesson(ui.state.lesson);
    ui.context.api.request = async () => { submitted = true; };
    ui.find("#written-answer").value = "   ";
    await ui.context.submitAnswer({ preventDefault() {} });
    assert.equal(submitted, false);
    assert.match(ui.find("#answer-error").textContent, /Add your answer/);
});

test("an old lesson response cannot reopen the app after logout", async () => {
    let resolveExercises;
    const ui = setupUI({ getAll: () => new Promise(resolve => { resolveExercises = resolve; }) });
    const loading = ui.context.openLesson(ui.state.lesson);
    ui.context.logout();
    resolveExercises([{ id: 17, kind: "text", prompt: "Old question", xp_reward: 10 }]);
    await loading;
    assert.equal(ui.find("#app-shell").hidden, true);
    assert.equal(ui.find("#auth-screen").hidden, false);
    assert.equal(ui.state.user, null);
});
