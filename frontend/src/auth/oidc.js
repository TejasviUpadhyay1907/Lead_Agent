const issuer = (import.meta.env.VITE_OIDC_ISSUER || '').replace(/\/$/, '');
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || '';
const apiScope = import.meta.env.VITE_OIDC_API_SCOPE || '';
const redirectUri = import.meta.env.VITE_OIDC_REDIRECT_URI || `${window.location.origin}/`;
const requestedScopes = import.meta.env.VITE_OIDC_SCOPE || `openid profile ${apiScope}`.trim();

let providerMetadata;
let accessToken = null;
let idToken = null;
let expiresAt = 0;

export const demoMode = import.meta.env.DEV && import.meta.env.VITE_DEMO_MODE !== 'false';
export const oidcConfigured = Boolean(issuer && clientId && apiScope);

async function getMetadata() {
    if (!providerMetadata) {
        providerMetadata = fetch(`${issuer}/.well-known/openid-configuration`)
            .then(response => {
                if (!response.ok) throw new Error('Identity provider discovery failed.');
                return response.json();
            })
            .then(metadata => {
                if (!metadata.authorization_endpoint || !metadata.token_endpoint || metadata.issuer !== issuer) {
                    throw new Error('Identity provider metadata does not match the configured issuer.');
                }
                return metadata;
            });
    }
    return providerMetadata;
}

function randomValue() {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function challengeFor(verifier) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function decodeJwtPayload(token) {
    const payload = token.split('.')[1]?.replace(/-/g, '+').replace(/_/g, '/');
    if (!payload) throw new Error('Identity provider returned an invalid ID token.');
    return JSON.parse(atob(payload));
}

export async function beginSignIn() {
    if (!oidcConfigured) throw new Error('Configure VITE_OIDC_ISSUER, VITE_OIDC_CLIENT_ID, and VITE_OIDC_API_SCOPE first.');
    const metadata = await getMetadata();
    const state = randomValue();
    const nonce = randomValue();
    const verifier = randomValue();
    sessionStorage.setItem('leadrescue.oidc.transaction', JSON.stringify({ state, nonce, verifier }));

    const authorize = new URL(metadata.authorization_endpoint);
    authorize.searchParams.set('response_type', 'code');
    authorize.searchParams.set('client_id', clientId);
    authorize.searchParams.set('redirect_uri', redirectUri);
    authorize.searchParams.set('scope', requestedScopes);
    authorize.searchParams.set('state', state);
    authorize.searchParams.set('nonce', nonce);
    authorize.searchParams.set('code_challenge', await challengeFor(verifier));
    authorize.searchParams.set('code_challenge_method', 'S256');
    window.location.assign(authorize);
}

export async function completeSignIn() {
    const url = new URL(window.location.href);
    const code = url.searchParams.get('code');
    if (!code) return false;
    const transaction = JSON.parse(sessionStorage.getItem('leadrescue.oidc.transaction') || 'null');
    sessionStorage.removeItem('leadrescue.oidc.transaction');
    if (!transaction || url.searchParams.get('state') !== transaction.state) {
        throw new Error('Sign-in state validation failed. Start sign-in again.');
    }

    const metadata = await getMetadata();
    const response = await fetch(metadata.token_endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            grant_type: 'authorization_code',
            client_id: clientId,
            code,
            redirect_uri: redirectUri,
            code_verifier: transaction.verifier,
        }),
    });
    if (!response.ok) throw new Error('The identity provider could not complete sign-in.');
    const tokens = await response.json();
    if (!tokens.access_token || !tokens.id_token) throw new Error('Identity provider did not return the required tokens.');
    const idClaims = decodeJwtPayload(tokens.id_token);
    const idAudiences = Array.isArray(idClaims.aud) ? idClaims.aud : [idClaims.aud];
    if (idClaims.nonce !== transaction.nonce || idClaims.iss !== issuer || !idAudiences.includes(clientId)) {
        throw new Error('Identity token validation failed.');
    }

    accessToken = tokens.access_token;
    idToken = tokens.id_token;
    expiresAt = Date.now() + Math.max(0, Number(tokens.expires_in || 0) - 30) * 1000;
    window.history.replaceState({}, document.title, `${url.pathname}${url.hash}`);
    return true;
}

export function getAccessToken() {
    return accessToken && Date.now() < expiresAt ? accessToken : null;
}

export function clearAccessToken() {
    accessToken = null;
    idToken = null;
    expiresAt = 0;
}

export async function signOut() {
    const tokenHint = idToken;
    clearAccessToken();
    if (!issuer || !clientId) return;
    try {
        const metadata = await getMetadata();
        if (metadata.end_session_endpoint) {
            const logout = new URL(metadata.end_session_endpoint);
            logout.searchParams.set('client_id', clientId);
            logout.searchParams.set('post_logout_redirect_uri', redirectUri);
            if (tokenHint) logout.searchParams.set('id_token_hint', tokenHint);
            window.location.assign(logout);
            return;
        }
    } catch { /* Local sign-out still clears the in-memory access token. */ }
    window.location.assign(redirectUri);
}
