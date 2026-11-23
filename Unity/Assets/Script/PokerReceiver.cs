using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

public class PokerReceiver : MonoBehaviour
{
    [Header("Python Connection")]
    [Tooltip("Keep animations and TCP processing running when Unity loses focus.")]
    public bool runInBackground = true;

    public string host = "127.0.0.1";
    public int port = 8765;

    [Header("Visual Managers")]
    public CardManager cardManager;
    public ChipManager chipManager;

    [Header("Fly Animations")]
    [Tooltip("Element 0 = Fly1, 1 = Fly2, 2 = Fly3, 3 = Fly4")]
    public FlyAnimationController[] flies;

    [Header("Fly Labels")]
    [Tooltip("Element 0 = Fly1 label, 1 = Fly2 label, 2 = Fly3 label, 3 = Fly4 label")]
    public FlyLabel[] flyLabels;

    [Header("Live Pot + Board Card Pictures")]
    [Tooltip("Created automatically when missing; may also be assigned in Inspector.")]
    public PokerTableHUD tableHUD;

    [Serializable]
    private class PokerMessage
    {
        public string type;
        public int seat;
        public string action;
        public float amount;
        public string[] cards;
        public string street;
        public int session;
        public int hand;
        public int button;
        public int small_blind;
        public int big_blind;
        public bool session_over;
        public int session_winner;
        public int[] winners;
    }

    private TcpListener listener;
    private TcpClient client;
    private StreamReader reader;
    private StreamWriter writer;
    private Thread networkThread;
    private volatile bool running;

    private readonly object writerLock = new object();
    private readonly ConcurrentQueue<Action> mainThreadActions =
        new ConcurrentQueue<Action>();

    private void Start()
    {
        // Do not freeze the scene when switching to the Python terminal.
        // Stopping Play Mode still closes TCP; Python V38 handles reconnect.
        if (runInBackground)
            Application.runInBackground = true;
        ResolveReferences();
        StartServer();
    }

    private void ResolveReferences()
    {
        if (cardManager == null)
            cardManager = FindFirstObjectByType<CardManager>();

        if (chipManager == null)
            chipManager = FindFirstObjectByType<ChipManager>();

        // Prefer a single explicit TableHUD; otherwise reuse an existing one.
        // Never auto-create an additional renderer if there is already a HUD.
        PokerTableHUD selectedHUD = PokerTableHUD.GetPrimaryHUD();
        if (selectedHUD == null)
            selectedHUD = gameObject.AddComponent<PokerTableHUD>();
        tableHUD = selectedHUD;

        Debug.Log("[PokerReceiver] Active POT HUD: " +
            (tableHUD != null ? tableHUD.gameObject.name : "NULL"));

        // Zawsze budujemy tablice 4 seatow. W starej scenie bylo wpisane tylko
        // Fly1, przez co pozostale miejsca nigdy nie mogly uruchomic animacji.
        FlyAnimationController[] old = flies;
        FlyAnimationController[] resolved = new FlyAnimationController[4];

        FlyLabel[] oldLabels = flyLabels;
        FlyLabel[] resolvedLabels = new FlyLabel[4];

        for (int seat = 0; seat < 4; seat++)
        {
            GameObject flyObject = GameObject.Find("Fly" + (seat + 1));

            if (flyObject != null)
            {
                FlyAnimationController controller =
                    flyObject.GetComponent<FlyAnimationController>();

                Animator animator = flyObject.GetComponent<Animator>();

                // Jezeli Fly2/Fly3/Fly4 sa kopiami modelu z Animatorem, ale bez
                // naszego kontrolera, dodajemy go automatycznie w runtime.
                if (controller == null && animator != null)
                {
                    controller = flyObject.AddComponent<FlyAnimationController>();
                    controller.animator = animator;
                }
                else if (controller != null && controller.animator == null)
                {
                    controller.animator = animator;
                }

                // Animation Events PickUp()/ReleaseToBet() are sent to the same
                // GameObject as Animator. Make sure every fly has AnchorHold,
                // not only Fly1.
                AnchorHold hold = flyObject.GetComponent<AnchorHold>();
                if (hold == null)
                    hold = flyObject.AddComponent<AnchorHold>();

                if (hold.handAnchor == null)
                {
                    hold.handAnchor = FindDeepChildStartingWith(flyObject.transform, "HandAnchor");
                    if (hold.handAnchor == null)
                        hold.handAnchor = FindDeepChildExact(flyObject.transform, "tarsal_claw_T1_left");
                }

                if (hold.betAnchor == null)
                {
                    GameObject bet = GameObject.Find("BetAnchors" + (seat + 1));
                    if (bet != null)
                        hold.betAnchor = bet.transform;
                }

                resolved[seat] = controller;

                // Label can live on Fly itself or on a child object above the fly.
                FlyLabel label = flyObject.GetComponentInChildren<FlyLabel>(true);
                if (label != null)
                {
                    label.SetSeat(seat);
                    resolvedLabels[seat] = label;
                }
            }

            // Fallback do recznie przypisanych elementow z Inspectora.
            if (resolved[seat] == null && old != null && seat < old.Length)
                resolved[seat] = old[seat];

            if (resolvedLabels[seat] == null && oldLabels != null && seat < oldLabels.Length)
            {
                resolvedLabels[seat] = oldLabels[seat];

                if (resolvedLabels[seat] != null)
                    resolvedLabels[seat].SetSeat(seat);
            }
        }

        flies = resolved;
        flyLabels = resolvedLabels;

        Debug.Log(
            "[PokerReceiver] refs | cards=" + (cardManager != null) +
            " chips=" + (chipManager != null) +
            " Fly1=" + (flies[0] != null) +
            " Fly2=" + (flies[1] != null) +
            " Fly3=" + (flies[2] != null) +
            " Fly4=" + (flies[3] != null) +
            " Labels=" +
            (flyLabels[0] != null) + "/" +
            (flyLabels[1] != null) + "/" +
            (flyLabels[2] != null) + "/" +
            (flyLabels[3] != null)
        );

        for (int seat = 0; seat < 4; seat++)
        {
            if (flies[seat] == null)
                continue;
            AnchorHold hold = flies[seat].GetComponent<AnchorHold>();
            Debug.Log(
                "[PokerReceiver] Fly" + (seat + 1) +
                " AnchorHold=" + (hold != null) +
                " hand=" + (hold != null && hold.handAnchor != null ? hold.handAnchor.name : "NULL") +
                " bet=" + (hold != null && hold.betAnchor != null ? hold.betAnchor.name : "NULL")
            );
        }
    }

    private void Update()
    {
        while (mainThreadActions.TryDequeue(out Action action))
        {
            try
            {
                action?.Invoke();
            }
            catch (Exception e)
            {
                Debug.LogError("[PokerReceiver] Main thread error:\n" + e);
            }
        }
    }

    private void StartServer()
    {
        if (running)
            return;

        running = true;
        networkThread = new Thread(NetworkLoop) { IsBackground = true };
        networkThread.Start();
    }

    private void NetworkLoop()
    {
        try
        {
            listener = new TcpListener(IPAddress.Parse(host), port);
            listener.Start();
            Debug.Log($"PokerReceiver listening on {host}:{port}");

            while (running)
            {
                try
                {
                    Debug.Log("[PokerReceiver] Waiting for Python...");
                    client = listener.AcceptTcpClient();
                    Debug.Log("[PokerReceiver] Python connected!");

                    NetworkStream stream = client.GetStream();
                    reader = new StreamReader(stream);

                    lock (writerLock)
                    {
                        writer = new StreamWriter(stream) { AutoFlush = true };
                    }

                    while (running && client != null && client.Connected)
                    {
                        string line = reader.ReadLine();
                        if (line == null)
                        {
                            Debug.Log("[PokerReceiver] Python disconnected.");
                            break;
                        }

                        line = line.Trim();
                        if (line.Length == 0)
                            continue;

                        Debug.Log("[PYTHON -> UNITY] " + line);
                        HandleMessage(line);
                    }
                }
                catch (ThreadAbortException)
                {
                    // Unity zatrzymuje Play Mode / przeladowuje domenę.
                    return;
                }
                catch (ObjectDisposedException)
                {
                    if (!running)
                        return;
                }
                catch (IOException)
                {
                    if (running)
                        Debug.LogWarning("[PokerReceiver] Python connection lost.");
                }
                catch (SocketException e)
                {
                    if (running)
                        Debug.LogWarning("[PokerReceiver] Socket error: " + e.Message);
                }
                catch (Exception e)
                {
                    if (running)
                        Debug.LogError("[PokerReceiver] Client error:\n" + e);
                }
                finally
                {
                    CloseClient();
                }
            }
        }
        catch (ThreadAbortException)
        {
            // Normalne przy zatrzymywaniu Play Mode w edytorze Unity.
        }
        catch (ObjectDisposedException)
        {
            // Listener zostal zamkniety podczas wychodzenia z Play Mode.
        }
        catch (Exception e)
        {
            if (running)
                Debug.LogError("[PokerReceiver] Server error:\n" + e);
        }
    }

    private void HandleMessage(string line)
    {
        if (line.StartsWith("{"))
        {
            HandleJsonMessage(line);
            return;
        }

        if (line.StartsWith("ANIM|", StringComparison.OrdinalIgnoreCase))
        {
            HandleOldAnimationMessage(line);
            return;
        }

        if (string.Equals(line, "PING", StringComparison.OrdinalIgnoreCase))
        {
            SendToPython("PONG");
            return;
        }

        Debug.Log("[PokerReceiver] Unhandled message: " + line);
    }

    private void HandleJsonMessage(string json)
    {
        try
        {
            PokerMessage msg = JsonUtility.FromJson<PokerMessage>(json);

            if (msg == null || string.IsNullOrWhiteSpace(msg.type))
            {
                Debug.LogWarning("[PokerReceiver] Invalid JSON: " + json);
                return;
            }

            string type = msg.type.Trim().ToLowerInvariant();

            switch (type)
            {
                case "animation":
                case "animate":
                {
                    int seat = msg.seat;
                    string pokerAction = msg.action;
                    float amount = msg.amount;

                    mainThreadActions.Enqueue(() =>
                        PlayPokerAnimation(seat, pokerAction, amount)
                    );
                    return;
                }

                case "new_hand":
                    mainThreadActions.Enqueue(() =>
                    {
                        cardManager?.NewHand();
                        chipManager?.NewHand();
                        tableHUD?.NewHand();

                        for (int i = 0; i < 4; i++)
                        {
                            if (flyLabels != null && i < flyLabels.Length && flyLabels[i] != null)
                                flyLabels[i].ResetForNewHand();
                        }

                        Debug.Log("[PokerReceiver] NEW HAND");
                    });
                    return;

                case "hole_cards":
                {
                    int seat = msg.seat;
                    string[] cards = msg.cards;

                    mainThreadActions.Enqueue(() =>
                    {
                        if (cards != null && cards.Length >= 2)
                            cardManager?.SetHoleCards(seat, cards);

                        // Use original textures (Resources/cards) for HUD thumbnails.
                        if (flyLabels != null && seat >= 0 && seat < flyLabels.Length)
                            flyLabels[seat]?.SetHoleCards(cards);
                    });
                    return;
                }

                case "board":
                {
                    string[] cards = msg.cards;
                    mainThreadActions.Enqueue(() =>
                    {
                        cardManager?.SetBoard(cards);
                        tableHUD?.SetBoard(cards);
                    });
                    return;
                }

                case "stack":
                {
                    int seat = msg.seat;
                    int amount = Mathf.RoundToInt(msg.amount);
                    mainThreadActions.Enqueue(() =>
                    {
                        chipManager?.SetStack(seat, amount);

                        if (flyLabels != null && seat >= 0 && seat < flyLabels.Length)
                            flyLabels[seat]?.SetStack(amount);
                    });
                    return;
                }

                case "bet":
                {
                    int seat = msg.seat;
                    int amount = Mathf.RoundToInt(msg.amount);
                    mainThreadActions.Enqueue(() => chipManager?.SetBet(seat, amount));
                    return;
                }

                case "pot":
                {
                    int amount = Mathf.RoundToInt(msg.amount);
                    mainThreadActions.Enqueue(() =>
                    {
                        chipManager?.SetPot(amount);
                        tableHUD?.SetPot(amount);
                    });
                    return;
                }

                case "collect_bets":
                {
                    mainThreadActions.Enqueue(() =>
                        StartCoroutine(CollectBetsAndReply())
                    );
                    return;
                }

                case "award_pot":
                {
                    int winnerSeat = msg.seat;
                    mainThreadActions.Enqueue(() =>
                        StartCoroutine(AwardPotAndReply(winnerSeat))
                    );
                    return;
                }

                case "turn":
                {
                    int seat = msg.seat;

                    mainThreadActions.Enqueue(() =>
                    {
                        if (flyLabels != null)
                        {
                            for (int i = 0; i < flyLabels.Length; i++)
                            {
                                if (flyLabels[i] != null)
                                    flyLabels[i].SetThinking(i == seat);
                            }
                        }

                        Debug.Log("[PokerReceiver] TURN seat=" + seat);
                    });

                    return;
                }

                case "action":
                {
                    int seat = msg.seat;
                    string action = msg.action;
                    int amount = Mathf.RoundToInt(msg.amount);

                    mainThreadActions.Enqueue(() =>
                    {
                        if (flyLabels != null && seat >= 0 && seat < flyLabels.Length)
                            flyLabels[seat]?.SetAction(action, amount);

                        Debug.Log(
                            "[PokerReceiver] ACTION seat=" + seat +
                            " action=" + action +
                            " amount=" + amount
                        );
                    });

                    return;
                }

                case "hand_end":
                    mainThreadActions.Enqueue(() =>
                    {
                        if (flyLabels != null)
                        {
                            for (int i = 0; i < flyLabels.Length; i++)
                            {
                                if (flyLabels[i] != null)
                                    flyLabels[i].ConfirmHandEnded();
                            }
                        }

                        Debug.Log("[PokerReceiver] HAND END - elimination confirmed using final stacks");
                    });
                    return;

                default:
                    Debug.Log("[PokerReceiver] JSON message: " + type);
                    return;
            }
        }
        catch (Exception e)
        {
            Debug.LogError(
                "[PokerReceiver] JSON ERROR:\n" + e + "\nJSON:\n" + json
            );
        }
    }

    private IEnumerator CollectBetsAndReply()
    {
        if (chipManager == null)
        {
            Debug.LogWarning("[PokerReceiver] collect_bets: ChipManager missing");
            SendChipFlowDone("collect_bets");
            yield break;
        }

        Debug.Log("[PokerReceiver] CHIP FLOW: BetAnchors -> PotAnchor");
        chipManager.CollectBetsToPot();

        while (chipManager.IsFlowBusy)
            yield return null;

        SendChipFlowDone("collect_bets");
    }

    private IEnumerator AwardPotAndReply(int winnerSeat)
    {
        if (chipManager == null)
        {
            Debug.LogWarning("[PokerReceiver] award_pot: ChipManager missing");
            SendChipFlowDone("award_pot", winnerSeat);
            yield break;
        }

        Debug.Log("[PokerReceiver] CHIP FLOW: PotAnchor -> winner seat=" + winnerSeat);
        chipManager.AwardPotToWinner(winnerSeat);

        while (chipManager.IsFlowBusy)
            yield return null;

        SendChipFlowDone("award_pot", winnerSeat);
    }

    private void SendChipFlowDone(string flow, int seat = -1)
    {
        string json = "{\"type\":\"chip_flow_done\",\"flow\":\"" + flow + "\"";

        if (seat >= 0)
            json += ",\"seat\":" + seat;

        json += "}";
        SendToPython(json);
    }

    private void HandleOldAnimationMessage(string line)
    {
        string[] parts = line.Split('|');
        if (parts.Length < 3)
            return;

        if (!int.TryParse(parts[1], out int player))
            return;

        string pokerAction = parts[2].Trim().ToUpperInvariant();
        float amount = 0f;

        if (parts.Length >= 4)
        {
            float.TryParse(
                parts[3],
                NumberStyles.Any,
                CultureInfo.InvariantCulture,
                out amount
            );
        }

        mainThreadActions.Enqueue(() =>
            PlayPokerAnimation(player, pokerAction, amount)
        );
    }

    private void PlayPokerAnimation(int player, string pokerAction, float amount)
    {
        if (flies == null || player < 0 || player >= flies.Length)
        {
            Debug.LogError("[PokerReceiver] Invalid fly index: " + player);
            SendAnimationDone(player);
            return;
        }

        FlyAnimationController fly = flies[player];
        if (fly == null)
        {
            Debug.LogError("[PokerReceiver] Missing fly controller for seat " + player);
            SendAnimationDone(player);
            return;
        }

        string animation = ConvertPokerActionToAnimation(pokerAction);

        Debug.Log(
            "[PokerReceiver] Fly " + player +
            " | action=" + pokerAction +
            " | animation=" + animation +
            " | amount=" + amount
        );

        if (animation == "NONE" || animation == "IDLE")
        {
            SendAnimationDone(player);
            return;
        }

        if (animation == "FOLD")
        {
            FoldCardController foldController = fly.GetComponent<FoldCardController>();
            if (foldController == null)
            {
                Debug.LogWarning(
                    "[PokerReceiver] Fly " + player +
                    " does not have FoldCardController on the Animator GameObject. " +
                    "The fly can animate but the cards will not be picked up or thrown."
                );
            }
        }

        // CALL/RAISE use a temporary visual bundle made from the Python amount.
        // The authoritative bet/stack is still sent by Python after the animation.
        if ((animation == "CALL" || animation == "RAISE") && amount > 0f)
        {
            GameObject animatedChips = chipManager != null
                ? chipManager.CreateAnimatedActionChips(player, Mathf.RoundToInt(amount))
                : null;

            AnchorHold hold = fly.GetComponent<AnchorHold>();
            if (hold != null && animatedChips != null)
                hold.SetChip(animatedChips);
        }

        fly.PlayAction(
            animation,
            () =>
            {
                Debug.Log(
                    "[PokerReceiver] Fly " + player +
                    " finished " + animation
                );
                SendAnimationDone(player);
            }
        );
    }

    private string ConvertPokerActionToAnimation(string action)
    {
        if (string.IsNullOrWhiteSpace(action))
            return "NONE";

        action = action.Trim().ToUpperInvariant();

        if (action == "THINK")
            return "THINK";

        if (action == "FOLD")
            return "FOLD";

        if (action == "CALL")
            return "CALL";

        if (
            action == "ALL-IN" ||
            action == "ALL_IN" ||
            action == "ALLIN" ||
            action == "ALL IN"
        )
            return "RAISE";

        if (
            action == "RAISE" ||
            action.Contains("RAISE") ||
            action.Contains("BET") ||
            action.Contains("POT")
        )
            return "RAISE";

        if (action == "IDLE")
            return "IDLE";

        // CHECK does not have a dedicated animation clip yet.
        return "NONE";
    }

    private void SendAnimationDone(int player)
    {
        SendToPython(
            "{\"type\":\"animation_done\",\"seat\":" + player + "}"
        );
    }

    public void SendToPython(string message)
    {
        lock (writerLock)
        {
            if (writer == null)
            {
                Debug.LogWarning("[PokerReceiver] Cannot send - Python not connected.");
                return;
            }

            try
            {
                writer.WriteLine(message);
                writer.Flush();
                Debug.Log("[UNITY -> PYTHON] " + message);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PokerReceiver] Send failed: " + e.Message);
            }
        }
    }

    private void CloseClient()
    {
        lock (writerLock)
        {
            try { writer?.Close(); } catch { }
            writer = null;
        }

        try { reader?.Close(); } catch { }
        reader = null;

        try { client?.Close(); } catch { }
        client = null;
    }

    private void StopServer()
    {
        if (!running)
            return;

        running = false;
        CloseClient();

        try { listener?.Stop(); } catch { }
        listener = null;

        Debug.Log("[PokerReceiver] Server stopped.");
    }

    private Transform FindDeepChildExact(Transform root, string exactName)
    {
        if (root == null)
            return null;

        foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
        {
            if (child.name == exactName)
                return child;
        }

        return null;
    }

    private Transform FindDeepChildStartingWith(Transform root, string prefix)
    {
        if (root == null)
            return null;

        foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
        {
            if (child.name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                return child;
        }

        return null;
    }

    private void OnDestroy()
    {
        StopServer();
    }

    private void OnApplicationQuit()
    {
        StopServer();
    }
}
