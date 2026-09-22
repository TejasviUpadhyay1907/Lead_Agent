import React, { createContext, useContext } from 'react';
import { beginSignIn, clearAccessToken, completeSignIn, demoMode, getAccessToken, oidcConfigured, signOut } from './oidc';

const AuthContext = createContext({ demoMode, signOut });
export const useAuth = () => useContext(AuthContext);

export function AuthGate({ children }) {
    const [status, setStatus] = React.useState(demoMode ? 'ready' : 'checking');
    const [error, setError] = React.useState('');

    React.useEffect(() => {
        if (demoMode) return;
        const expired = () => { clearAccessToken(); setStatus('signed-out'); setError('Your company session has expired. Sign in again.'); };
        window.addEventListener('leadrescue-auth-expired', expired);
        return () => window.removeEventListener('leadrescue-auth-expired', expired);
    }, []);

    React.useEffect(() => {
        if (demoMode) return;
        if (!oidcConfigured) {
            setStatus('setup');
            return;
        }
        (async () => {
            try {
            const current = new URL(window.location.href);
            if (current.searchParams.has('error')) throw new Error(current.searchParams.get('error_description') || 'Sign-in was cancelled.');
            await completeSignIn();
            setStatus(getAccessToken() ? 'ready' : 'signed-out');
            } catch (reason) {
                setError(reason.message || 'Sign-in could not be completed.');
                setStatus('signed-out');
            }
        })();
    }, []);

    if (status === 'checking') return <div className="auth-screen"><div className="auth-card"><div className="auth-mark">LR</div><p>Checking your sign-in…</p></div></div>;
    if (status !== 'ready') return <div className="auth-screen"><div className="auth-card"><div className="auth-mark">LR</div><span className="eyebrow">LEADRESCUE AI</span><h1>{status === 'setup' ? 'Sign-in is not configured' : 'Welcome back'}</h1><p>{status === 'setup' ? 'Set the OIDC issuer, client ID, API scope, and redirect URI in the frontend deployment settings.' : 'Sign in with your company account to open the lead workspace.'}</p>{error && <p className="auth-error" role="alert">{error}</p>}{status === 'signed-out' && <button className="btn-primary auth-submit" onClick={() => beginSignIn().catch(reason => setError(reason.message))}>Continue with company sign-in</button>}</div></div>;

    return <AuthContext.Provider value={{ demoMode, signOut }}>{children}</AuthContext.Provider>;
}
