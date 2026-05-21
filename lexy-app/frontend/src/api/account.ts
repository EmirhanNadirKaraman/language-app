// Account self-service API.
//
// deleteAccount() permanently removes the authenticated user. The backend
// returns 204; on success we clear the local token + email so any subsequent
// request would 401 even if the user clicks "Delete" again before the page
// navigates away.

import { apiUrl } from './_baseUrl';
import { assertOk, signalAuthExpired } from './_http';

export async function deleteAccount(token: string): Promise<void> {
    const res = await fetch(apiUrl('/api/v1/account'), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
    });
    await assertOk(res, 'Failed to delete account');
    // Clear stored auth and signal layout to navigate home. Use 'unauthorized'
    // because the token is now functionally invalid (its user row is gone).
    signalAuthExpired('unauthorized');
}
