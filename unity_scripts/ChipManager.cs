using UnityEngine;
using System.Collections.Generic;

public class ChipManager : MonoBehaviour
{
    [Header("One chip prefab (Cylinder)")]
    public GameObject chipPrefab;

    [Header("Player stack anchors")]
    public Transform player1Stack;
    public Transform player2Stack;
    public Transform player3Stack;
    public Transform player4Stack;

    [Header("Current bet anchors")]
    public Transform player1Bet;
    public Transform player2Bet;
    public Transform player3Bet;
    public Transform player4Bet;

    [Header("Centre pot")]
    public Transform potAnchor;

    [Header("Visual spacing")]
    public float chipHeight = 0.025f;
    public int maxPerColumn = 8;
    public float columnSpacing = 0.22f;

    private readonly Dictionary<int, List<GameObject>> stackObjects = new Dictionary<int, List<GameObject>>();
    private readonly Dictionary<int, List<GameObject>> betObjects = new Dictionary<int, List<GameObject>>();
    private readonly List<GameObject> potObjects = new List<GameObject>();

    private static readonly int[] Denominations = { 500, 100, 25, 5, 1 };

    void Awake()
    {
        for (int seat = 0; seat < 4; seat++)
        {
            stackObjects[seat] = new List<GameObject>();
            betObjects[seat] = new List<GameObject>();
        }
    }

    public void NewHand()
    {
        // Player stacks persist between hands and will be refreshed by Python.
        // Only current bets and the centre pot belong to the old hand.
        for (int seat = 0; seat < 4; seat++)
            ClearList(betObjects[seat]);

        ClearList(potObjects);
    }

    public void SetStack(int seat, int amount)
    {
        Transform anchor = GetStackAnchor(seat);
        if (anchor == null) return;

        RebuildAmount(stackObjects[seat], anchor, Mathf.Max(0, amount), "Stack");
    }

    public void SetBet(int seat, int amount)
    {
        Transform anchor = GetBetAnchor(seat);
        if (anchor == null) return;

        RebuildAmount(betObjects[seat], anchor, Mathf.Max(0, amount), "Bet");
    }

    public void SetPot(int amount)
    {
        if (potAnchor == null)
        {
            Debug.LogError("ChipManager: Pot Anchor is not assigned.");
            return;
        }

        RebuildAmount(potObjects, potAnchor, Mathf.Max(0, amount), "Pot");
    }

    private Transform GetStackAnchor(int seat)
    {
        switch (seat)
        {
            case 0: return player1Stack;
            case 1: return player2Stack;
            case 2: return player3Stack;
            case 3: return player4Stack;
            default:
                Debug.LogError("ChipManager: invalid seat " + seat);
                return null;
        }
    }

    private Transform GetBetAnchor(int seat)
    {
        switch (seat)
        {
            case 0: return player1Bet;
            case 1: return player2Bet;
            case 2: return player3Bet;
            case 3: return player4Bet;
            default:
                Debug.LogError("ChipManager: invalid seat " + seat);
                return null;
        }
    }

    private void RebuildAmount(List<GameObject> objects, Transform anchor, int amount, string groupName)
    {
        ClearList(objects);

        if (amount <= 0) return;
        if (chipPrefab == null)
        {
            Debug.LogError("ChipManager: Chip Prefab is not assigned.");
            return;
        }

        int remaining = amount;
        int visualIndex = 0;

        foreach (int denomination in Denominations)
        {
            int count = remaining / denomination;
            remaining %= denomination;

            for (int i = 0; i < count; i++)
            {
                int column = visualIndex / Mathf.Max(1, maxPerColumn);
                int level = visualIndex % Mathf.Max(1, maxPerColumn);

                Vector3 localOffset = new Vector3(
                    column * columnSpacing,
                    level * chipHeight,
                    0f
                );

                GameObject chip = Instantiate(chipPrefab, anchor);
                chip.transform.localPosition = localOffset;
                chip.transform.localRotation = Quaternion.identity;
                chip.name = groupName + "_Chip_" + denomination;

                Renderer renderer = chip.GetComponentInChildren<Renderer>();
                if (renderer != null)
                    renderer.material.color = ColorForDenomination(denomination);

                objects.Add(chip);
                visualIndex++;
            }
        }
    }

    private Color ColorForDenomination(int denomination)
    {
        switch (denomination)
        {
            case 500: return new Color(0.12f, 0.12f, 0.12f); // black
            case 100: return new Color(0.08f, 0.22f, 0.70f); // blue
            case 25:  return new Color(0.08f, 0.55f, 0.20f); // green
            case 5:   return new Color(0.75f, 0.08f, 0.08f); // red
            default:  return new Color(0.90f, 0.90f, 0.90f); // white / 1
        }
    }

    private void ClearList(List<GameObject> objects)
    {
        for (int i = 0; i < objects.Count; i++)
        {
            if (objects[i] != null)
                Destroy(objects[i]);
        }
        objects.Clear();
    }
}
