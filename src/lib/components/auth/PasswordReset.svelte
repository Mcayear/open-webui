<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	export let email = '';
	export let onClose: () => void;
	const i18n = getContext('i18n');
	let sent = false;
	let busy = false;
	let token = '';
	let password = '';
	let confirmation = '';
	let error = '';

	async function submit() {
		if (busy) return;
		error = '';
		if (sent && confirmation !== password) {
			error = $i18n.t('Passwords do not match.');
			return;
		}
		busy = true;
		try {
			const response = await fetch(
				`${WEBUI_API_BASE_URL}/auths/password-reset/${sent ? 'confirm' : 'request'}`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(
						sent ? { email, reset_token: token.trim(), new_password: password } : { email }
					)
				}
			);
			if (!response.ok) throw new Error((await response.json()).detail);
			if (sent) {
				toast.success($i18n.t('Password reset. Sign in with your new password.'));
				onClose();
			} else sent = true;
		} catch (e) {
			error = $i18n.t(e instanceof Error ? e.message : 'Authentication failed. Please try again.');
		} finally {
			busy = false;
		}
	}
</script>

<form
	class="my-auto mx-auto w-full max-w-sm flex flex-col gap-4 text-sm"
	on:submit|preventDefault={submit}
>
	<h1 class="text-2xl">{$i18n.t('Reset password')}</h1>
	<label class="text-left"
		>{$i18n.t('Email')}
		<input
			class="mt-1 w-full rounded-lg bg-transparent border px-3 py-2"
			type="email"
			autocomplete="email"
			bind:value={email}
			readonly={sent}
			required
		/>
	</label>
	{#if sent}
		<p role="status" class="text-left text-gray-600 dark:text-gray-400">
			{$i18n.t(
				'If this email belongs to a local account, check your inbox for a reset code. It expires in 15 minutes.'
			)}
		</p>
		<label class="text-left"
			>{$i18n.t('Reset code')}
			<input
				class="mt-1 w-full rounded-lg bg-transparent border px-3 py-2"
				autocomplete="one-time-code"
				autocapitalize="none"
				spellcheck="false"
				bind:value={token}
				required
			/>
		</label>
		<label class="text-left"
			>{$i18n.t('New Password')}
			<input
				class="mt-1 w-full rounded-lg bg-transparent border px-3 py-2"
				type="password"
				autocomplete="new-password"
				bind:value={password}
				required
			/>
		</label>
		<label class="text-left"
			>{$i18n.t('Confirm Password')}
			<input
				class="mt-1 w-full rounded-lg bg-transparent border px-3 py-2"
				type="password"
				autocomplete="new-password"
				bind:value={confirmation}
				required
			/>
		</label>
	{/if}
	{#if error}<p role="alert" class="text-red-600 dark:text-red-400">{error}</p>{/if}
	<button
		class="w-full rounded-full py-2.5 bg-gray-700/5 dark:bg-gray-100/10 disabled:opacity-50"
		type="submit"
		disabled={busy}
	>
		{sent ? $i18n.t('Reset password') : $i18n.t('Send reset code')}
	</button>
	{#if sent}
		<button
			type="button"
			disabled={busy}
			on:click={() => {
				sent = false;
				token = password = confirmation = error = '';
			}}>{$i18n.t('Request another code')}</button
		>
	{/if}
	<button type="button" disabled={busy} class="underline" on:click={onClose}
		>{$i18n.t('Back to sign in')}</button
	>
</form>
