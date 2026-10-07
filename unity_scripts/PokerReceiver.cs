using UnityEngine;
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Collections.Concurrent;

[Serializable]
public class PokerMessage
{
    public string type;
    public int seat;
    public int amount;
    public string[] cards;
}

public class PokerReceiver : MonoBehaviour
{
    public CardManager cardManager;
    public ChipManager chipManager;

    private TcpListener listener;
    private Thread listenerThread;
    private readonly ConcurrentQueue<PokerMessage> queue = new ConcurrentQueue<PokerMessage>();

    void Start()
    {
        listenerThread = new Thread(Listen);
        listenerThread.IsBackground = true;
        listenerThread.Start();
        Debug.Log("PokerReceiver listening on 127.0.0.1:8765");
    }

    void Listen()
    {
        try
        {
            listener = new TcpListener(IPAddress.Loopback, 8765);
            listener.Start();

            while (true)
            {
                using TcpClient client = listener.AcceptTcpClient();
                using StreamReader reader = new StreamReader(client.GetStream());

                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    PokerMessage message = JsonUtility.FromJson<PokerMessage>(line);
                    if (message != null)
                        queue.Enqueue(message);
                }
            }
        }
        catch (Exception e)
        {
            Debug.Log("PokerReceiver stopped: " + e.Message);
        }
    }

    void Update()
    {
        while (queue.TryDequeue(out PokerMessage msg))
        {
            switch (msg.type)
            {
                case "new_hand":
                    if (cardManager != null) cardManager.NewHand();
                    if (chipManager != null) chipManager.NewHand();
                    break;

                case "hole_cards":
                    if (cardManager != null) cardManager.SetHoleCards(msg.seat, msg.cards);
                    break;

                case "board":
                    if (cardManager != null) cardManager.SetBoard(msg.cards);
                    break;

                case "stack":
                    if (chipManager != null) chipManager.SetStack(msg.seat, msg.amount);
                    break;

                case "bet":
                    if (chipManager != null) chipManager.SetBet(msg.seat, msg.amount);
                    break;

                case "pot":
                    if (chipManager != null) chipManager.SetPot(msg.amount);
                    break;
            }
        }
    }

    void OnDestroy()
    {
        listener?.Stop();
    }
}
