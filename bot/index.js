const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionType } = require('discord.js');
require('dotenv').config();

const PY_API = (process.env.PY_API_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');
const MAIN_TOKEN = process.env.DISCORD_BOT_TOKEN;
if (!MAIN_TOKEN) { console.error('[FATAL] DISCORD_BOT_TOKEN missing'); process.exit(1); }

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent, GatewayIntentBits.DirectMessages] });
const pendingConfirms = new Map();

async function pyPost(path, body) {
    try { const res = await fetch(`${PY_API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return await res.json(); } catch (e) { return { success: false, error: e.message }; }
}
async function pyGet(path) {
    try { const res = await fetch(`${PY_API}${path}`); return await res.json(); } catch (e) { return { success: false, error: e.message }; }
}

function parsePairs(input) {
    if (!input || !input.trim()) return null;
    const out = [];
    for (const chunk of input.split(',')) {
        const s = chunk.trim(); if (!s) continue;
        const idx = s.lastIndexOf('-'); if (idx === -1) return null;
        const token = s.slice(0, idx).trim(); const chanStr = s.slice(idx + 1).trim();
        if (!token || token.length < 50 || !/^\d+$/.test(chanStr)) return null;
        out.push({ token, channelId: parseInt(chanStr, 10) });
    }
    return out.length ? out : null;
}

async function verifyToken(token) {
    try { const res = await fetch('https://discord.com/api/users/@me', { headers: { Authorization: token } }); if (res.status !== 200) return { ok: false, reason: `HTTP ${res.status}` }; const data = await res.json(); return { ok: true, username: `${data.username}#${data.discriminator || '0'}` }; } catch (e) { return { ok: false, reason: e.message }; }
}
async function verifyChannel(token, channelId) {
    try { const res = await fetch(`https://discord.com/api/channels/${channelId}`, { headers: { Authorization: token } }); if (res.status !== 200) return { ok: false, reason: `HTTP ${res.status}` }; const data = await res.json(); return { ok: true, name: data.name || `channel-${channelId}` }; } catch (e) { return { ok: false, reason: e.message }; }
}

function confirmRow(userId) {
    return new ActionRowBuilder().addComponents(
        new ButtonBuilder().setCustomId(`confirm:${userId}`).setLabel('Confirm & Start').setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId(`cancel:${userId}`).setLabel('Cancel').setStyle(ButtonStyle.Danger)
    );
}
function makeAddModal(userId) {
    const modal = new ModalBuilder().setCustomId(`addworkers:${userId}`).setTitle('Add Worker Tokens & Channels');
    const input = new TextInputBuilder().setCustomId('pairs').setLabel('Token-Channel pairs').setPlaceholder('TOKEN1-CHANNELID1,TOKEN2-CHANNELID2').setStyle(TextInputStyle.Paragraph).setMinLength(50).setMaxLength(3500).setRequired(true);
    modal.addComponents(new ActionRowBuilder().addComponents(input));
    return modal;
}
async function buildPanelEmbed(userId) {
    const status = await pyGet(`/api/user/${userId}/status`);
    const workers = (status.success && status.workers) ? status.workers : [];
    const embed = new EmbedBuilder().setTitle('GhoSty OwO - Panel').setColor(0x5865F2).setDescription('**Token Security**\nOnly you can manage your workers.');
    if (workers.length) {
        const lines = workers.map(w => `**Worker #${w.worker_num}** - ${w.username || 'Connecting...'}\n- <#${w.channel_id}> | ${w.valid ? 'Valid' : 'Invalid'} | ${w.running ? 'Running' : 'Stopped'}`);
        embed.addFields({ name: `Your Workers (${workers.length})`, value: lines.join('\n\n'), inline: false });
    } else { embed.addFields({ name: 'Your Workers', value: 'None yet. Click **Add Workers**.', inline: false }); }
    embed.addFields({ name: 'How To Add', value: '1. Click **Add Workers**\n2. Paste `TOKEN1-CHANNELID1,TOKEN2-CHANNELID2`\n3. Confirm below.', inline: false });
    return embed;
}
function panelRow(userId) {
    return new ActionRowBuilder().addComponents(
        new ButtonBuilder().setCustomId(`open_add:${userId}`).setLabel('Add Workers').setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId(`refresh:${userId}`).setLabel('Refresh').setStyle(ButtonStyle.Secondary)
    );
}

client.once('ready', () => { console.log(`[CTRL] Ready as ${client.user.tag}`); });

client.on('messageCreate', async (msg) => {
    if (msg.author.bot || msg.content.trim().toLowerCase() !== '.panel') return;
    const userId = msg.author.id;
    await pyGet(`/api/user/${userId}/ensure?username=${encodeURIComponent(msg.author.username)}`);
    await msg.reply({ embeds: [await buildPanelEmbed(userId)], components: [panelRow(userId)] });
});

client.on('interactionCreate', async (interaction) => {
    if (interaction.isButton()) {
        const [action, ownerId] = interaction.customId.split(':');
        if (ownerId && interaction.user.id !== ownerId) return interaction.reply({ content: 'Not your panel.', ephemeral: true });
        if (action === 'open_add') return interaction.showModal(makeAddModal(interaction.user.id));
        if (action === 'refresh') return interaction.update({ embeds: [await buildPanelEmbed(interaction.user.id)], components: [panelRow(interaction.user.id)] });
        if (action === 'confirm') {
            const pending = pendingConfirms.get(interaction.user.id);
            if (!pending) return interaction.reply({ content: 'Expired.', ephemeral: true });
            await interaction.deferUpdate();
            const added = [];
            for (const w of pending.workers) { const r = await pyPost(`/api/user/${interaction.user.id}/add_worker`, { token: w.token, channel_id: w.channelId, username: w.username }); if (r.success) added.push(w); }
            pendingConfirms.delete(interaction.user.id);
            return interaction.editReply({ embeds: [new EmbedBuilder().setTitle('Workers Started').setColor(0x10B981).setDescription(`**${added.length} worker(s) launched**`)], components: [] });
        }
        if (action === 'cancel') { pendingConfirms.delete(interaction.user.id); return interaction.update({ content: 'Cancelled.', embeds: [], components: [] }); }
    }
    if (interaction.type === InteractionType.ModalSubmit && interaction.customId.startsWith('addworkers:')) {
        const pairs = parsePairs(interaction.fields.getTextInputValue('pairs'));
        if (!pairs) return interaction.reply({ content: 'Invalid format.', ephemeral: true });
        await interaction.deferReply({ ephemeral: true });
        const verified = []; const failed = [];
        for (let i = 0; i < pairs.length; i++) {
            const tv = await verifyToken(pairs[i].token);
            if (!tv.ok) { failed.push(`Pair ${i+1}: Token invalid`); continue; }
            const cv = await verifyChannel(pairs[i].token, pairs[i].channelId);
            if (!cv.ok) { failed.push(`Pair ${i+1}: Channel invalid`); continue; }
            verified.push({ token: pairs[i].token, channelId: pairs[i].channelId, username: tv.username });
        }
        if (!verified.length) return interaction.editReply({ content: `No valid pairs.\n${failed.join('\n')}` });
        pendingConfirms.set(interaction.user.id, { workers: verified });
        return interaction.editReply({ embeds: [new EmbedBuilder().setTitle('Verification Result').setColor(0x10B981).setDescription(`**${verified.length} ready to start.**`)], components: [confirmRow(interaction.user.id)] });
    }
});

client.login(MAIN_TOKEN);
