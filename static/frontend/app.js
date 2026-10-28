/* Simple page state. All content comes from the existing Django API. */
const state = {
    user: null,
    progress: null,
    courses: [],
    course: null,
    lessons: [],
    lesson: null,
    exercises: [],
    exerciseIndex: 0,
    submission: null,
    page: "dashboard",
};
let authMode = "login";
let viewVersion = 0;
let pollTimer = null;
let pollCount = 0;
let submitting = false;

function element(selector) {
    return document.querySelector(selector);
}

function setText(selector, value) {
    element(selector).textContent = value;
}

function showMessage(selector, text, informational = false) {
    const message = element(selector);
    message.textContent = text;
    message.hidden = !text;
    message.classList.toggle("info", informational);
}

function stopPolling() {
    clearTimeout(pollTimer);
    pollTimer = null;
}

function switchAuthMode(mode) {
    authMode = mode;
    const registering = mode === "register";
    element("#email-field").hidden = !registering;
    element("#auth-email").disabled = !registering;
    element("#auth-email").required = registering;
    element("#password-help").hidden = !registering;
    element("#auth-password").autocomplete = registering ? "new-password" : "current-password";
    element("#auth-password").minLength = registering ? 8 : 1;
    setText("#auth-title", registering ? "Start something good." : "Good to see you.");
    setText("#auth-description", registering ? "Your next chapter starts right here." : "Pick up where you left off.");
    setText("#auth-submit", registering ? "Create your account →" : "Log in →");
    for (const modeName of ["login", "register"]) {
        const button = element("#" + modeName + "-tab");
        button.classList.toggle("active", modeName === mode);
        button.setAttribute("aria-pressed", String(modeName === mode));
    }
    showMessage("#auth-message", "");
}

function showAuth(message = "") {
    viewVersion += 1;
    stopPolling();
    state.user = null;
    state.progress = null;
    state.submission = null;
    submitting = false;
    for (const item of document.querySelectorAll("[data-stat]")) {
        item.textContent = "—";
    }
    element("#app-shell").hidden = true;
    element("#auth-screen").hidden = false;
    element("#auth-form").reset();
    switchAuthMode("login");
    showMessage("#auth-message", message, true);
}

function logout() {
    api.clearTokens();
    showAuth("You’re logged out. Your progress is saved for next time.");
    element("#auth-username").focus();
}

async function authenticate(event) {
    event.preventDefault();
    const username = element("#auth-username").value.trim();
    const password = element("#auth-password").value;
    const email = element("#auth-email").value.trim();
    setAuthBusy(true);
    showMessage("#auth-message", "");
    try {
        if (authMode === "register") {
            await api.request("/api/v1/auth/register/", {
                method: "POST", authenticated: false,
                body: { username: username, email: email, password: password },
            });
            switchAuthMode("login");
            showMessage("#auth-message", "Account created. Signing you in…", true);
        }
        const tokens = await api.request("/api/v1/auth/token/", {
            method: "POST", authenticated: false,
            body: { username: username, password: password },
        });
        api.saveTokens(tokens);
        await openSession();
    } catch (error) {
        showMessage("#auth-message", error.message);
    } finally {
        element("#auth-password").value = "";
        setAuthBusy(false);
    }
}

function setAuthBusy(busy) {
    element("#auth-submit").disabled = busy;
    element("#login-tab").disabled = busy;
    element("#register-tab").disabled = busy;
    setText("#auth-submit", busy ? "Just a moment…" : authMode === "register" ? "Create your account →" : "Log in →");
}

async function openSession() {
    const version = ++viewVersion;
    const user = await api.request("/api/v1/me/");
    if (version !== viewVersion) {
        return;
    }
    state.user = user;
    const initial = user.username.charAt(0).toUpperCase();
    setText("#header-username", user.username);
    setText("#header-avatar", initial);
    setText("#profile-avatar", initial);
    setText("#profile-username", user.username);
    setText("#profile-email", user.email || "No email address provided.");
    setText("#welcome-message", "Welcome, " + user.username + ". Let’s make your next small step count.");
    element("#auth-screen").hidden = true;
    element("#app-shell").hidden = false;
    await navigate("dashboard");
}

function selectView(page, title, eyebrow) {
    viewVersion += 1;
    stopPolling();
    submitting = false;
    state.page = page;
    for (const view of document.querySelectorAll(".view")) {
        view.hidden = view.id !== page + "-view";
    }
    const activePage = ["lessons", "exercise"].includes(page) ? "courses" : page;
    for (const button of document.querySelectorAll(".nav-button")) {
        const active = button.dataset.page === activePage;
        button.classList.toggle("active", active);
        if (active) {
            button.setAttribute("aria-current", "page");
        } else {
            button.removeAttribute("aria-current");
        }
    }
    setText("#page-title", title);
    setText("#page-eyebrow", eyebrow);
    showMessage("#page-message", "");
    element("#page-loading").hidden = true;
    element("#refresh-button").disabled = false;
    element("#page-title").focus({ preventScroll: true });
    return viewVersion;
}

function setLoading(loading) {
    element("#page-loading").hidden = !loading;
    element("#refresh-button").disabled = loading;
    element("#" + state.page + "-view").hidden = loading;
}

async function navigate(page) {
    if (!state.user) {
        return;
    }
    const titles = { dashboard: "Overview", courses: "My learning", profile: "My profile" };
    const version = selectView(page, titles[page], "YOUR JOURNEY, ONE STEP AT A TIME");
    setLoading(true);
    try {
        const progress = await api.request("/api/v1/me/progress/");
        if (version !== viewVersion) {
            return;
        }
        state.progress = progress;
        renderProgress();
        if (page !== "profile") {
            const courses = await api.getAll("/api/v1/courses/");
            if (version !== viewVersion) {
                return;
            }
            state.courses = courses;
            renderCourses(page === "dashboard" ? "#dashboard-courses" : "#course-list");
        }
    } catch (error) {
        if (version === viewVersion) {
            showMessage("#page-message", error.message + " Use Refresh to try again.");
        }
    } finally {
        if (version === viewVersion) {
            setLoading(false);
        }
    }
}

function renderProgress() {
    for (const item of document.querySelectorAll("[data-stat]")) {
        item.textContent = state.progress[item.dataset.stat].toLocaleString();
    }
}

function emptyState(container, text) {
    const message = document.createElement("p");
    message.className = "empty-state";
    message.textContent = text;
    container.append(message);
}

function renderCourses(selector) {
    const container = element(selector);
    container.replaceChildren();
    if (state.courses.length === 0) {
        emptyState(container, "No courses are available yet. Check back soon for your first lesson.");
    }
    for (const course of state.courses) {
        const card = element("#course-card-template").content.cloneNode(true);
        card.querySelector(".course-level").textContent = "ENGLISH · " + course.level;
        card.querySelector(".course-name").textContent = course.title;
        card.querySelector(".course-description").textContent = course.description;
        card.querySelector(".open-course").addEventListener("click", () => openCourse(course));
        container.append(card);
    }
}

async function openCourse(course) {
    state.course = course;
    state.lesson = null;
    const version = selectView("lessons", "One lesson at a time", "MY LEARNING / COURSE");
    setLoading(true);
    try {
        const lessons = await api.getAll("/api/v1/courses/" + course.id + "/lessons/");
        const progress = await api.request("/api/v1/me/progress/");
        if (version !== viewVersion) {
            return;
        }
        state.lessons = lessons;
        state.progress = progress;
        renderLessons();
    } catch (error) {
        if (version === viewVersion) {
            element("#lesson-list").replaceChildren();
            showMessage("#page-message", error.message + " Use Refresh to try again.");
        }
    } finally {
        if (version === viewVersion) {
            setLoading(false);
        }
    }
}

function renderLessons() {
    setText("#course-title", state.course.title);
    setText("#course-description", state.course.description);
    setText("#course-level", "ENGLISH · " + state.course.level);
    const completed = state.lessons.filter(lesson => state.progress.completed_lesson_ids.includes(lesson.id)).length;
    setText("#course-progress-label", completed + " of " + state.lessons.length + " lessons complete");
    element("#course-progress-bar").value = state.lessons.length ? completed / state.lessons.length * 100 : 0;
    setText("#lesson-count", state.lessons.length + " lessons");
    const container = element("#lesson-list");
    container.replaceChildren();
    if (state.lessons.length === 0) {
        emptyState(container, "This course’s lessons are on their way. Explore another course for now.");
    }
    for (const lesson of state.lessons) {
        const done = state.progress.completed_lesson_ids.includes(lesson.id);
        const card = element("#lesson-card-template").content.cloneNode(true);
        card.querySelector(".lesson-card").classList.toggle("completed", done);
        card.querySelector(".lesson-number").textContent = done ? "✓" : String(lesson.order).padStart(2, "0");
        card.querySelector(".lesson-status").textContent = done ? "COMPLETED" : "READY WHEN YOU ARE";
        card.querySelector(".lesson-name").textContent = lesson.title;
        card.querySelector(".lesson-description").textContent = lesson.description;
        card.querySelector(".open-lesson").textContent = done ? "Practice again →" : "Start lesson →";
        card.querySelector(".open-lesson").addEventListener("click", () => openLesson(lesson));
        container.append(card);
    }
}

async function openLesson(lesson) {
    state.lesson = lesson;
    state.submission = null;
    const version = selectView("exercise", lesson.title, "MY LEARNING / PRACTICE");
    setLoading(true);
    try {
        const exercises = await api.getAll("/api/v1/lessons/" + lesson.id + "/exercises/");
        const progress = await api.request("/api/v1/me/progress/");
        if (version !== viewVersion) {
            return;
        }
        state.exercises = exercises;
        state.progress = progress;
        state.exerciseIndex = 0;
        setLoading(false);
        renderExercise();
    } catch (error) {
        if (version === viewVersion) {
            element("#exercise-card").hidden = true;
            element("#lesson-summary").hidden = true;
            showMessage("#page-message", error.message + " Use Refresh to try again.");
        }
    } finally {
        if (version === viewVersion) {
            setLoading(false);
        }
    }
}

function renderLessonProgress() {
    const completed = state.exercises.filter(exercise => state.progress.completed_exercise_ids.includes(exercise.id)).length;
    setText("#lesson-completion-label", completed + " of " + state.exercises.length + " completed");
    element("#lesson-progress-bar").value = state.exercises.length ? completed / state.exercises.length * 100 : 0;
}

function renderExercise() {
    stopPolling();
    viewVersion += 1;
    submitting = false;
    state.submission = null;
    renderLessonProgress();
    if (state.exerciseIndex >= state.exercises.length) {
        showLessonSummary();
        return;
    }
    element("#exercise-card").hidden = false;
    element("#lesson-summary").hidden = true;
    element("#submission-result").hidden = true;
    element("#exercise-actions").hidden = true;
    element("#check-status").hidden = true;
    element("#answer-fields").disabled = false;
    element("#submit-answer").disabled = false;
    element("#refresh-button").disabled = false;
    showMessage("#answer-error", "");
    const exercise = state.exercises[state.exerciseIndex];
    const labels = { multiple_choice: "CHOOSE THE RIGHT WORD", text: "FILL IN THE BLANK", writing: "PUT IT INTO WORDS" };
    setText("#exercise-position", "Exercise " + (state.exerciseIndex + 1) + " of " + state.exercises.length);
    setText("#exercise-kind", labels[exercise.kind] || "PRACTICE");
    setText("#exercise-xp", "✦ " + exercise.xp_reward + " XP");
    setText("#exercise-prompt", exercise.prompt);
    const instruction = exercise.kind === "writing"
        ? "Take your time. Write in English and submit for feedback."
        : "Give it a try. Every answer is a chance to learn.";
    setText("#exercise-instruction", instruction);
    setText("#submit-answer", exercise.kind === "writing" ? "Get writing feedback →" : "Check answer →");
    renderAnswerInput(exercise);
}

function renderAnswerInput(exercise) {
    const container = element("#answer-inputs");
    container.replaceChildren();
    if (exercise.kind === "multiple_choice") {
        for (const key of Object.keys(exercise.options)) {
            const label = document.createElement("label");
            label.className = "option";
            const radio = document.createElement("input");
            radio.type = "radio";
            radio.name = "answer";
            radio.value = key;
            radio.required = true;
            const text = document.createElement("span");
            text.textContent = exercise.options[key];
            label.append(radio, text);
            container.append(label);
        }
        return;
    }
    const label = document.createElement("label");
    label.htmlFor = "written-answer";
    label.textContent = "Your answer";
    const input = document.createElement(exercise.kind === "writing" ? "textarea" : "input");
    input.id = "written-answer";
    input.name = "answer";
    input.maxLength = 2000;
    input.required = true;
    input.placeholder = exercise.kind === "writing" ? "Start writing here…" : "Type your answer…";
    const count = document.createElement("p");
    count.className = "character-count";
    count.textContent = "0 / 2,000 characters";
    input.addEventListener("input", () => {
        count.textContent = input.value.length.toLocaleString() + " / 2,000 characters";
    });
    container.append(label, input, count);
}

async function submitAnswer(event) {
    event.preventDefault();
    if (submitting || state.submission) {
        return;
    }
    const input = element("#answer-inputs input:checked") || element("#written-answer");
    const answer = input ? input.value.trim() : "";
    if (!answer) {
        showMessage("#answer-error", "Add your answer before continuing.");
        return;
    }
    const version = viewVersion;
    const exercise = state.exercises[state.exerciseIndex];
    submitting = true;
    element("#submit-answer").disabled = true;
    element("#answer-fields").disabled = true;
    element("#refresh-button").disabled = true;
    setText("#submit-answer", "Submitting…");
    showMessage("#answer-error", "");
    try {
        const submission = await api.request("/api/v1/exercises/" + exercise.id + "/submit/", {
            method: "POST", body: { answer: answer },
        });
        if (version !== viewVersion) {
            return;
        }
        state.submission = submission;
        pollCount = 0;
        await displaySubmission(submission, version);
    } catch (error) {
        if (version === viewVersion) {
            showMessage("#answer-error", error.message);
            element("#answer-fields").disabled = false;
            element("#submit-answer").disabled = false;
            setText("#submit-answer", "Submit answer →");
        }
    } finally {
        if (version === viewVersion) {
            submitting = false;
            element("#refresh-button").disabled = false;
        }
    }
}

function renderResultBase(submission) {
    element("#submission-result").hidden = false;
    element("#submission-result").className = "result-panel";
    element("#mock-notice").hidden = submission.provider !== "mock";
    element("#feedback-details").hidden = true;
    element("#check-status").hidden = true;
    setText("#result-xp", "");
    setText("#result-symbol", "◌");
}

async function displaySubmission(submission, version) {
    state.submission = submission;
    renderResultBase(submission);
    if (["pending", "processing", "retrying"].includes(submission.status)) {
        const labels = { pending: "Your writing is in the queue", processing: "Reviewing your writing…", retrying: "Trying the feedback service again…" };
        setText("#result-title", labels[submission.status]);
        setText("#result-message", "You can stay here while your feedback is prepared. Your answer has been saved.");
        setText("#submit-answer", "Answer submitted");
        schedulePoll(version);
        return;
    }
    stopPolling();
    element("#try-again").hidden = submission.status === "completed" && submission.is_correct;
    setText("#next-exercise", state.exerciseIndex + 1 < state.exercises.length ? "Next exercise →" : "Finish practice →");
    setText("#submit-answer", "Answer submitted");
    if (submission.status === "completed") {
        renderCompletedResult(submission);
    } else {
        renderFailedResult(submission);
    }
    try {
        const progress = await api.request("/api/v1/me/progress/");
        if (version === viewVersion) {
            state.progress = progress;
            renderProgress();
            renderLessonProgress();
        }
    } catch (error) {
        if (version === viewVersion) {
            showMessage("#page-message", "Your answer is saved, but progress could not refresh. " + error.message);
        }
    } finally {
        if (version === viewVersion) {
            element("#exercise-actions").hidden = false;
        }
    }
}

function renderCompletedResult(submission) {
    const correct = submission.is_correct;
    element("#submission-result").classList.toggle("incorrect", !correct);
    setText("#result-symbol", correct ? "✓" : "↻");
    setText("#result-title", correct ? "Nicely done!" : "A little more practice");
    setText("#result-xp", "+" + submission.xp_awarded + " XP");
    let message = "Take another look and try again when you’re ready.";
    if (correct) {
        message = submission.xp_awarded > 0
            ? "One more step forward. Your progress has been saved."
            : "You’ve already earned XP for this exercise. Keep practicing as often as you like.";
    }
    setText("#result-message", message);
    if (submission.feedback) {
        element("#feedback-details").hidden = false;
        setText("#feedback-score", "Writing score: " + submission.feedback.score + " / 100");
        setText("#feedback-explanation", submission.feedback.explanation);
        const corrections = element("#feedback-corrections");
        corrections.replaceChildren();
        for (const correction of submission.feedback.corrections) {
            const item = document.createElement("li");
            item.textContent = correction;
            corrections.append(item);
        }
    }
}

function renderFailedResult(submission) {
    element("#submission-result").classList.add("failed");
    setText("#result-symbol", "!");
    const unavailable = submission.status === "unavailable";
    setText("#result-title", unavailable ? "Writing feedback isn’t available yet" : "Feedback couldn’t be completed");
    const messages = {
        ai_not_configured: "The feedback provider isn’t configured. Your answer is saved, "
            + "but no evaluation or XP was awarded. You can continue with other exercises.",
        queue_unavailable: "The background service couldn’t queue your answer. Try again later or continue with another exercise.",
        provider_unavailable: "The feedback service is unavailable after several attempts. Please try again later.",
        provider_timeout: "The feedback service took too long to respond. Please try again later.",
        feedback_failed: "Your answer was saved, but the feedback task failed. Please try again later.",
    };
    setText("#result-message", messages[submission.error_code] || "Your answer is saved, but feedback could not be completed. Please try again later.");
}

function schedulePoll(version) {
    if (pollCount >= 60) {
        setText("#result-message", "This is taking longer than expected. Your answer is saved. Check its status again in a moment.");
        element("#check-status").hidden = false;
        return;
    }
    stopPolling();
    pollTimer = setTimeout(() => pollSubmission(version), 2000);
}

async function pollSubmission(version) {
    if (version !== viewVersion || !state.submission) {
        return;
    }
    pollCount += 1;
    try {
        const submission = await api.request("/api/v1/submissions/" + state.submission.id + "/");
        if (version === viewVersion) {
            await displaySubmission(submission, version);
        }
    } catch (error) {
        if (version === viewVersion) {
            setText("#result-message", "Your answer is saved. " + error.message);
            element("#check-status").hidden = false;
        }
    }
}

function showLessonSummary() {
    element("#exercise-card").hidden = true;
    element("#lesson-summary").hidden = false;
    setText("#exercise-position", "Practice summary");
    const done = state.progress.completed_lesson_ids.includes(state.lesson.id);
    setText("#lesson-summary-title", done ? "A lesson well learned." : "Every attempt counts.");
    let message = "Complete each exercise successfully to finish this lesson. "
        + "Review your answers and give it another go.";
    if (state.exercises.length === 0) {
        message = "There are no exercises in this lesson yet. Try another lesson for now.";
    } else if (done) {
        message = "You’ve completed every exercise in this lesson. "
            + "Keep exploring, or practice again to build your confidence.";
    }
    setText("#lesson-summary-text", message);
    element("#review-lesson").hidden = state.exercises.length === 0;
}

async function refreshCurrentPage() {
    if (state.page === "lessons") {
        await openCourse(state.course);
    } else if (state.page === "exercise") {
        if (state.submission && ["pending", "processing", "retrying"].includes(state.submission.status)) {
            stopPolling();
            pollCount = 0;
            await pollSubmission(viewVersion);
        } else {
            await openLesson(state.lesson);
        }
    } else {
        await navigate(state.page);
    }
}

function bindEvents() {
    element("#login-tab").addEventListener("click", () => switchAuthMode("login"));
    element("#register-tab").addEventListener("click", () => switchAuthMode("register"));
    element("#auth-form").addEventListener("submit", authenticate);
    for (const button of document.querySelectorAll("[data-page]")) {
        button.addEventListener("click", () => navigate(button.dataset.page));
    }
    element("#logout-button").addEventListener("click", logout);
    element("#profile-logout").addEventListener("click", logout);
    element("#refresh-button").addEventListener("click", refreshCurrentPage);
    element("#back-to-courses").addEventListener("click", () => navigate("courses"));
    element("#back-to-lessons").addEventListener("click", () => openCourse(state.course));
    element("#answer-form").addEventListener("submit", submitAnswer);
    element("#try-again").addEventListener("click", renderExercise);
    element("#next-exercise").addEventListener("click", () => {
        state.exerciseIndex += 1;
        renderExercise();
    });
    element("#review-lesson").addEventListener("click", () => {
        state.exerciseIndex = 0;
        renderExercise();
    });
    element("#finish-lesson").addEventListener("click", () => openCourse(state.course));
    element("#check-status").addEventListener("click", () => {
        pollCount = 0;
        element("#check-status").hidden = true;
        pollSubmission(viewVersion);
    });
    document.addEventListener("auth:expired", () => showAuth("Your session expired. Log in again to continue."));
    window.addEventListener("pagehide", stopPolling);
}

async function initialize() {
    bindEvents();
    if (api.hasSession()) {
        setAuthBusy(true);
        try {
            await openSession();
        } catch (error) {
            showAuth(error.message);
        } finally {
            setAuthBusy(false);
        }
    }
}

initialize();
