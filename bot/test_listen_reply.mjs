/**
 * 監聽聊天室 Bot 系統回覆（用固定 sharedSecret）
 * 使用方式：node test_listen_reply.mjs <botEpub> <myPriv> <myEpub> [seconds]
 * 或直接從環境變數讀取
 */
import SEA from 'gun/sea.js';
import Gun from 'gun';

const RELAY_URL = process.env.GUN_RELAY_URL || 'https://gun-relay-bxdc.onrender.com/gun';
const CHATROOM = 'render_isolated_chat_room';
const LISTEN_SECS = parseInt(process.argv[5] || '60');

async function main() {
    // 從命令列取 keypair JSON
    const pairJson = process.argv[2];
    const botEpubArg = process.argv[3];

    if (!pairJson || !botEpubArg) {
        console.log('Usage: node test_listen_reply.mjs <pairJSON> <botEpub> [seconds]');
        console.log('Listening for any messages...');
    }

    const gun = Gun({ peers: [RELAY_URL], radisk: false, localStorage: false });

    let myPair, botEpub, sharedSecret;

    if (pairJson && botEpubArg) {
        myPair = JSON.parse(pairJson);
        botEpub = botEpubArg;
        sharedSecret = await SEA.secret(botEpub, myPair);
        console.log(`監聽聊天室（sharedSecret: ${sharedSecret.substring(0,15)}...）`);
    }

    console.log(`開始監聽 ${LISTEN_SECS} 秒...`);

    gun.get(CHATROOM).map().on(async (data, key) => {
        if (!data) return;

        // 嘗試解密
        if (sharedSecret) {
            try {
                const raw = await SEA.decrypt(data, sharedSecret);
                if (raw !== undefined && raw !== null) {
                    let text;
                    if (typeof raw === 'string') text = raw;
                    else if (raw && raw.text) text = raw.text;
                    else text = JSON.stringify(raw);

                    const time = new Date().toLocaleTimeString('zh-TW');
                    console.log(`\n[${time}] 解密成功 (key: ${key})`);
                    console.log(`內容: ${text.substring(0, 200)}${text.length > 200 ? '...' : ''}`);
                }
            } catch {}
        }

        // 也嘗試讀取未加密的 broadcast 格式 (bot=true)
        if (data.bot && data.text) {
            const time = new Date().toLocaleTimeString('zh-TW');
            console.log(`\n[${time}] Bot 廣播 (key: ${key})`);
            console.log(`內容: ${data.text.substring(0, 200)}`);
        }
    });

    await new Promise(r => setTimeout(r, LISTEN_SECS * 1000));
    console.log('\n監聽結束');
    process.exit(0);
}

main().catch(console.error);
