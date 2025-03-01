package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
	"github.com/joho/godotenv"
)

// Konfigurasi
var (
	TELEGRAM_BOT_TOKEN string
	DEEPSEEK_API_KEY   string
	DEEPSEEK_BASE_URL  = "https://api.deepseek.com/chat/completions"
	CONVERSATION_DIR   = "conversation"
)

const (
	SYSTEM_PROMT = `You are an advanced AI assistant named RyuBot Coder, specialized in programming,
  debugging, and generating code. You are capable of understanding complex software development concepts,
  identifying issues in code, fixing them, and generating high-quality, efficient code as required.
  Provide detailed explanations and recommendations when responding to user requests about software,
  coding, or debugging. Answer questions based on the language used by the user. If someone asks about
  you, you are an AI developed by @RyuDevpr using the DeepSeek model.`
)

var (
	dialogContext       = make(map[int64][]map[string]string)
	doalogContextMutext sync.Mutex
	currentModel        = "deepseek-chat"
	currentTemperature  = 1.3
	MAX_CONTEXT_LENGTH  = 30
)

func init() {
	err := godotenv.Load()
	if err != nil {
		log.Fatal("Gagal memuat .env")
	}

	TELEGRAM_BOT_TOKEN = os.Getenv("TELEGRAM_TOKEN")
	DEEPSEEK_API_KEY = os.Getenv("DEEPSEEK_API_KEY")

	if TELEGRAM_BOT_TOKEN == "" || DEEPSEEK_API_KEY == "" {
		log.Fatal("TELEGRAM_TOKEN dan DEEPSEEK_API_KEY harus diisi di.env")
	}

	os.MkdirAll(CONVERSATION_DIR, os.ModePerm)
}

func splitMessage(msg string, maxLength int) []string {
	var chunks []string
	for i := 0; i < len(msg); i += maxLength {
		end := i + maxLength
		if end > len(msg) {
			end = len(msg)
		}
		chunks = append(chunks, msg[i:end])
	}
	return chunks
}

func sanitizeFilename(name string) string {
	reg := regexp.MustCompile(`[\\/*?:"<>|]`)
	sanitized := reg.ReplaceAllString(name, "-")
	sanitized = strings.ReplaceAll(sanitized, " ", "-")
	if len(sanitized) > 20 {
		sanitized = sanitized[:20]
	}
	return strings.TrimSpace(sanitized)
}

func handleStart(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	keyboard := tgbotapi.NewReplyKeyboard(
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton("/deephelp"),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton("/deepclear"),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton("/deepmodel"),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton("/deepinfo"),
		),
	)

	msg := tgbotapi.NewMessage(update.Message.Chat.ID, "🤖 Halo! Saya Asisten Coding. Kirimkan kode/error Anda untuk analisis atau ajukan pertanyaan!")
	msg.ReplyMarkup = keyboard
	bot.Send(msg)
}

func handleClear(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	chat := update.Message.Chat

	var chatName string
	if chat.IsGroup() || chat.IsSuperGroup() {
		chatName = chat.Title
	} else {
		chatName = chat.FirstName
		if chatName == "" {
			chatName = chat.UserName
		}
		if chatName == "" {
			chatName = fmt.Sprintf("%d", chat.ID)
		}
	}

	sanitizedName := sanitizeFilename(chatName)
	timestamp := time.Now().Format("2006-01-02_15-04-05")
	filename := fmt.Sprintf("%s-%d-%s.json", sanitizedName, chat.ID, timestamp)
	filepath := filepath.Join(CONVERSATION_DIR, filename)

	if context, ok := dialogContext[chat.ID]; ok {
		data := map[string]interface{}{
			"chat_info": map[string]interface{}{
				"chat_id": chat.ID,
				"title":   chatName,
				"type":    chat.Type,
			},
			"model_info": map[string]interface{}{
				"model": "DeepSeek",
				"mode":  currentModel,
			},
			"context": context,
		}

		jsonData, err := json.MarshalIndent(data, "", "  ")
		if err != nil {
			log.Printf("Error marshaling JSON: %v", err)
			bot.Send(tgbotapi.NewMessage(chat.ID, "⚠️ Terjadi kesalahan saat menyimpan konteks percakapan."))
			return
		}

		err = ioutil.WriteFile(filepath, jsonData, 0644)
		if err != nil {
			log.Printf("Error writing file: %v", err)
			bot.Send(tgbotapi.NewMessage(chat.ID, "⚠️ Terjadi kesalahan saat menyimpan konteks percakapan."))
			return
		}

		bot.Send(tgbotapi.NewMessage(chat.ID, "ℹ️ Konteks percakapan dibersihkan."))
		log.Printf("Konteks disimpan ke: %s", filepath)
	} else {
		bot.Send(tgbotapi.NewMessage(chat.ID, "Tidak ada konteks percakapan yang perlu dibersihkan."))
	}

	delete(dialogContext, chat.ID)
}

func handleSwitchMode(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	if currentModel == "deepseek-chat" {
		currentModel = "deepseek-reasoner"
		currentTemperature = 0.0
	} else {
		currentModel = "deepseek-chat"
		currentTemperature = 1.3
	}
	msg := fmt.Sprintf("ℹ️ Mode percakapan berubah menjadi %s dengan temperature %.1f.", currentModel, currentTemperature)
	bot.Send(tgbotapi.NewMessage(update.Message.Chat.ID, msg))
}

func handleMessage(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	user := update.Message.From
	username := user.UserName
	if username == "" {
		username = fmt.Sprintf("%s %s", user.FirstName, user.LastName)
	}
	if username == "" {
		username = fmt.Sprintf("%d", user.ID)
	}

	chatID := update.Message.Chat.ID
	var userMsg string

	if update.Message.Chat.IsGroup() || update.Message.Chat.IsSuperGroup() {
		isMention := strings.HasPrefix(strings.ToLower(update.Message.Text), strings.ToLower(bot.Self.UserName))
		isReplyToBot := update.Message.ReplyToMessage != nil && update.Message.ReplyToMessage.From.ID == bot.Self.ID

		if !isMention && !isReplyToBot {
			return
		}

		if isMention {
			log.Printf("\nPertanyaan dari user: @%s\nModel: %s\nTemperature: %.1f", username, currentModel, currentTemperature)
			userMsg = strings.TrimPrefix(update.Message.Text, "@"+bot.Self.UserName)
			userMsg = strings.TrimSpace(userMsg)
		} else {
			userMsg = update.Message.Text
		}
	} else {
		userMsg = update.Message.Text
	}

	if userMsg == "" {
		bot.Send(tgbotapi.NewMessage(chatID, "Maaf saya hanya bisa merespon pesan text"))
		return
	}

	bot.Send(tgbotapi.NewChatAction(chatID, tgbotapi.ChatTyping))

	if _, ok := dialogContext[chatID]; !ok {
		dialogContext[chatID] = []map[string]string{}
	}

	dialogContext[chatID] = append(dialogContext[chatID], map[string]string{"role": "user", "content": userMsg})
	if len(dialogContext[chatID]) > MAX_CONTEXT_LENGTH {
		dialogContext[chatID] = dialogContext[chatID][len(dialogContext[chatID])-MAX_CONTEXT_LENGTH:]
	}

	fullContext := []map[string]string{{"role": "system", "content": SYSTEM_PROMT}}
	fullContext = append(fullContext, dialogContext[chatID]...)

	data := map[string]interface{}{
		"model":       currentModel,
		"messages":    fullContext,
		"temperature": currentTemperature,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		log.Printf("Error marshaling JSON: %v", err)
		bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Terjadi error: Kesalahan internal"))
		return
	}

	req, err := http.NewRequest("POST", DEEPSEEK_BASE_URL, bytes.NewBuffer(jsonData))
  if err != nil {
    log.Printf("Error creating request: %v", err)
    bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Terjadi error: Kesalahan internal"))
    return
  }

  req.Header.Set("Authorization", "Bearer "+DEEPSEEK_API_KEY)
  req.Header.Set("Content-Type", "application/json")

  client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("Error sending request: %v", err)
		bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Terjadi error: Kesalahan jaringan"))
		return
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Printf("Error sending request: %v", err)
		bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Terjadi error: Kesalahan jaringan"))
		return
	}

	var responseData map[string]interface{}
	err = json.Unmarshal(body, &responseData)
	if err != nil {
		log.Printf("Error unmarshalling JSON: %v", err)
    bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Terjadi error: Kesalahan memproses respon"))
    return
	}

	// log.Printf("Raw API res: %v", responseData)

	choices, ok := responseData["choices"].([]interface{})
	if !ok || len(choices) == 0 {
		log.Printf("Invalid API response: %v", responseData)
		bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Respon tidak valid dari AI."))
		return
	}

	choice, ok := choices[0].(map[string]interface{})
	if !ok {
		log.Printf("Invalid choice in API response: %v", choices[0])
		bot.Send(tgbotapi.NewMessage(chatID, "⚠️ AI tidak merespon"))
		return
	}

	message, ok := choice["message"].(map[string]interface{})
	if !ok {
		log.Printf("Invalid message in API response: %v", choice["message"])
		bot.Send(tgbotapi.NewMessage(chatID, "AI Tidak merespon."))
		return
	}

	botResponse, ok := message["content"].(string)
	if !ok {
		botResponse = "Gagal membuat respon."
	}

	dialogContext[chatID] = append(dialogContext[chatID], map[string]string{"role": "assistant", "content": botResponse})

	messageParts := splitMessage(botResponse, 4096)
	for _, part := range messageParts {
		msg := tgbotapi.NewMessage(chatID, part)
		msg.ParseMode = tgbotapi.ModeMarkdown
		_, err := bot.Send(msg)
		if err != nil {
			log.Printf("Error sending message %v", err)
			msg.ParseMode = ""
			_, err = bot.Send(msg)
			if err != nil {
				log.Printf("Error sending plain message %v", err)
				bot.Send(tgbotapi.NewMessage(chatID, "⚠️ Terjadi kesalahan saat mengirim pesan."))
			}
		}
	}
	log.Printf("Response berhasil dikirim kepada user: @%s\n", username)
}

func handleUnknownCommand(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	bot.Send(tgbotapi.NewMessage(update.Message.Chat.ID, "ℹ️ Perintah tersebut tidak tersedia."))
}

func handleInfo(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	chat := update.Message.Chat
	var title string
	if chat.IsGroup() || chat.IsSuperGroup() {
		title = chat.Title
	} else {
		title = chat.FirstName
		if title == "" {
			title = chat.UserName
		}
		if title == "" {
			title = fmt.Sprintf("%d", chat.ID)
		}
	}

	infoText := fmt.Sprintf(`
	ⓘ *Sekedar info*
	━━━━━━━━━━━━━━━━━━━━
	⤷ %s
	⤷ Model: %s
	⤷ Temperature: %.1f

	🤖 *Info model*
	━━━━━━━━━━━━━━━━━━━━
	⤷ *deepseek-chat*: Menggunakan model DeepSeek-V3
	⤷ *deepseek-reasoner*: Menggunakan model DeepSeek-R1

	📝 *Penggunaan temperature*
	━━━━━━━━━━━━━━━━━━━━
	⤷ *1.3*: Percakapan general
	⤷ *0.0*: Fokus ke coding/perhitungan
	`, title, currentModel, currentTemperature)

	msg := tgbotapi.NewMessage(update.Message.Chat.ID, infoText)
	msg.ParseMode = tgbotapi.ModeMarkdown
	bot.Send(msg)
}

func handleHelpCommand(bot *tgbotapi.BotAPI, update tgbotapi.Update) {
	helpText := `
	Perintah tersedia
	━━━━━━━━━━━━━━━━━━━━
	/start - untuk memulai bot
	/deepclear - untuk membersihkan konteks percakapan
	/deephelp - menampilkan pesan bantuan
	/deepcheck - menampilkan informasi tentang mode percakapan
	/deepmodel - untuk berganti model "chat" atau "reasoning"
	`

	bot.Send(tgbotapi.NewMessage(update.Message.Chat.ID, helpText))
}

func main() {
	bot, err := tgbotapi.NewBotAPI(TELEGRAM_BOT_TOKEN)
	if err != nil {
		log.Panic(err)
	}

	bot.Debug = true
	log.Printf("Authorized on account %s", bot.Self.UserName)

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60

	updates := bot.GetUpdatesChan(u)

	for update := range updates {
		if update.Message == nil {
			continue
		}

		switch update.Message.Command() {
		case "start":
			handleStart(bot, update)
		case "deepclear":
			handleClear(bot, update)
		case "deepmodel":
			handleSwitchMode(bot, update)
		case "deephelp":
			handleHelpCommand(bot, update)
		case "deepinfo":
			handleInfo(bot, update)
		default:
			if update.Message.IsCommand() {
				handleUnknownCommand(bot, update)
			} else {
				handleMessage(bot, update)
			}
		}
	}
}