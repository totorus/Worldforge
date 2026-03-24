class WSService {
  constructor() {
    this.ws = null;
    this.listeners = new Map();
    this.reconnectTimer = null;
    this.connected = false;
  }

  connect() {
    const token = localStorage.getItem("token");
    if (!token) return;

    // Close existing connection if any
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws?token=${token}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.connected = true;
      this._emit("connected", {});
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "ping") return;
        this._emit(data.type, data);
        this._emit("*", data); // wildcard listeners
      } catch (e) {
        console.error("WS parse error:", e);
      }
    };

    this.ws.onclose = () => {
      this.connected = false;
      this._emit("disconnected", {});
      // Auto-reconnect after 3s
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // prevent auto-reconnect
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  on(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(callback);
    // Return unsubscribe function
    return () => this.listeners.get(type)?.delete(callback);
  }

  _emit(type, data) {
    this.listeners.get(type)?.forEach((cb) => cb(data));
  }
}

export const wsService = new WSService();
