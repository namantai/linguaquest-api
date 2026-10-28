/* All HTTP and token handling lives here. No passwords are saved. */
const api = (() => {
    const accessKey = "linguaquest.access";
    const refreshKey = "linguaquest.refresh";
    let refreshPromise = null;

    function readToken(key) {
        try {
            return sessionStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function clearTokens() {
        try {
            sessionStorage.removeItem(accessKey);
            sessionStorage.removeItem(refreshKey);
        } catch (error) {
            // Storage may be disabled by browser privacy settings.
        }
    }

    function saveTokens(tokens) {
        try {
            sessionStorage.setItem(refreshKey, tokens.refresh);
            sessionStorage.setItem(accessKey, tokens.access);
        } catch (error) {
            clearTokens();
            throw new Error("Allow session storage in your browser to log in.");
        }
    }

    function expireSession() {
        clearTokens();
        document.dispatchEvent(new Event("auth:expired"));
    }

    function describeErrors(data, prefix = "") {
        if (typeof data === "string") {
            return prefix + data;
        }
        const messages = [];
        if (Array.isArray(data)) {
            for (const item of data) {
                messages.push(describeErrors(item, prefix));
            }
        } else if (data && typeof data === "object") {
            for (const key of Object.keys(data)) {
                const label = ["detail", "non_field_errors"].includes(key) ? "" : key + ": ";
                messages.push(describeErrors(data[key], label));
            }
        }
        return messages.filter(Boolean).join(" ");
    }

    function apiURL(path) {
        const url = new URL(path, window.location.origin);
        // Paginated URLs must never send a token to another website.
        if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/v1/")) {
            throw new Error("The server returned an unexpected API address.");
        }
        return url.href;
    }

    async function fetchJSON(path, method, body, accessToken) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);
        const headers = { Accept: "application/json" };
        if (accessToken) {
            headers.Authorization = "Bearer " + accessToken;
        }
        if (body !== null) {
            headers["Content-Type"] = "application/json";
        }
        try {
            const response = await fetch(apiURL(path), {
                method: method,
                headers: headers,
                body: body === null ? null : JSON.stringify(body),
                credentials: "omit",
                redirect: "error",
                signal: controller.signal,
            });
            let data;
            try {
                data = await response.json();
            } catch (error) {
                throw new Error("The server returned an unreadable response. Please try again.");
            }
            return { response: response, data: data };
        } catch (error) {
            if (error.name === "AbortError") {
                throw new Error("The request timed out. Check your connection and try again.");
            }
            if (error instanceof TypeError) {
                throw new Error("We couldn’t reach the server. Check your connection and try again.");
            }
            throw error;
        } finally {
            clearTimeout(timeout);
        }
    }

    async function refreshAccess() {
        const refreshToken = readToken(refreshKey);
        if (!refreshToken) {
            expireSession();
            throw new Error("Your session has expired. Please log in again.");
        }
        const result = await fetchJSON("/api/v1/auth/token/refresh/", "POST", {
            refresh: refreshToken,
        }, null);
        // A late refresh must not sign a user back in after logout or account change.
        if (readToken(refreshKey) !== refreshToken) {
            throw new Error("The session changed. Please try again.");
        }
        if (!result.response.ok) {
            if ([400, 401].includes(result.response.status)) {
                expireSession();
                throw new Error("Your session has expired. Please log in again.");
            }
            throw new Error("We couldn’t renew your session. Please try again shortly.");
        }
        saveTokens({
            access: result.data.access,
            refresh: result.data.refresh || refreshToken,
        });
    }

    async function request(path, options = {}) {
        const method = options.method || "GET";
        const body = options.body === undefined ? null : options.body;
        const authenticated = options.authenticated !== false;
        const originalToken = authenticated ? readToken(accessKey) : null;
        const originalSession = authenticated ? readToken(refreshKey) : null;
        let result = await fetchJSON(path, method, body, originalToken);
        if (result.response.status === 401 && authenticated) {
            if (readToken(refreshKey) !== originalSession) {
                throw new Error("The session changed. Please try again.");
            }
            // Share one refresh when dashboard requests expire at the same time.
            if (readToken(accessKey) === originalToken) {
                if (!refreshPromise) {
                    refreshPromise = refreshAccess().finally(() => {
                        refreshPromise = null;
                    });
                }
                await refreshPromise;
            }
            if (!readToken(accessKey)) {
                throw new Error("Your session has expired. Please log in again.");
            }
            const retrySession = readToken(refreshKey);
            result = await fetchJSON(path, method, body, readToken(accessKey));
            if (readToken(refreshKey) !== retrySession) {
                throw new Error("The session changed. Please try again.");
            }
            if (result.response.status === 401) {
                expireSession();
            }
        }
        if (!result.response.ok) {
            const error = new Error(result.response.status >= 500
                ? "Something went wrong on the server. Please try again shortly."
                : describeErrors(result.data) || "This request could not be completed.");
            error.status = result.response.status;
            throw error;
        }
        return result.data;
    }

    async function getAll(path) {
        const items = [];
        const visited = [];
        let next = path;
        while (next) {
            const address = apiURL(next);
            if (visited.includes(address)) {
                throw new Error("The server returned a repeated page. Please try again.");
            }
            visited.push(address);
            const page = await request(address);
            if (!Array.isArray(page.results)) {
                throw new Error("The list could not be loaded. Please try again.");
            }
            items.push(...page.results);
            next = page.next;
        }
        return items;
    }

    return {
        request: request,
        getAll: getAll,
        saveTokens: saveTokens,
        clearTokens: clearTokens,
        hasSession: () => Boolean(readToken(refreshKey)),
    };
})();
