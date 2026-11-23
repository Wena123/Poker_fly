using System.Collections;
using System.Collections.Generic;
using UnityEngine;

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

    [Header("Chip flow animation")]
    [Tooltip("Time for chips to move from player BetAnchors to PotAnchor.")]
    public float betToPotDuration = 0.45f;

    [Tooltip("Time for chips to move from PotAnchor to the winner stack.")]
    public float potToWinnerDuration = 0.65f;

    [Tooltip("Height of the small arc while chips are moving.")]
    public float moveArcHeight = 0.12f;

    [Tooltip("Small delay between individual chips. Set 0 for all chips at once.")]
    public float chipMoveStagger = 0.012f;

    private readonly Dictionary<int, List<GameObject>> stackObjects =
        new Dictionary<int, List<GameObject>>();

    private readonly Dictionary<int, List<GameObject>> betObjects =
        new Dictionary<int, List<GameObject>>();

    private readonly Dictionary<int, GameObject> animatedActionRoots =
        new Dictionary<int, GameObject>();

    private readonly List<GameObject> potObjects = new List<GameObject>();

    private static readonly int[] Denominations = { 500, 100, 25, 5, 1 };

    private Coroutine collectRoutine;
    private Coroutine awardRoutine;

    private bool collectingBets = false;
    private bool awardingPot = false;

    // If Python updates the authoritative pot while the Bet -> Pot animation
    // is running, remember it and rebuild the final pot only after the move.
    private int queuedPotAmount = -1;

    public bool IsFlowBusy => collectingBets || awardingPot;

    private void Awake()
    {
        for (int seat = 0; seat < 4; seat++)
        {
            stackObjects[seat] = new List<GameObject>();
            betObjects[seat] = new List<GameObject>();
            animatedActionRoots[seat] = null;
        }

        AutoAssignMissingAnchors();
    }

    // =========================================================
    // NEW HAND / CLEANUP
    // =========================================================

    public void NewHand()
    {
        // Important: stop old chip movement before the next hand begins.
        StopAllCoroutines();
        collectRoutine = null;
        awardRoutine = null;
        collectingBets = false;
        awardingPot = false;
        queuedPotAmount = -1;

        for (int seat = 0; seat < 4; seat++)
        {
            ClearList(betObjects[seat]);
            ClearAnimatedActionChips(seat);
        }

        ClearList(potObjects);

        Debug.Log("[ChipManager] NEW HAND -> cleared all BetAnchors and PotAnchor visuals");
    }

    // =========================================================
    // AUTHORITATIVE STACK / BET / POT FROM PYTHON
    // =========================================================

    public void SetStack(int seat, int amount)
    {
        if (!ValidSeat(seat))
            return;

        Transform anchor = GetStackAnchor(seat);
        if (anchor == null)
        {
            Debug.LogWarning("ChipManager: no stack anchor for seat " + seat);
            return;
        }

        RebuildAmount(
            stackObjects[seat],
            anchor,
            Mathf.Max(0, amount),
            "Stack"
        );

        Debug.Log("[ChipManager] STACK seat=" + seat + " amount=" + amount + " anchor=" + anchor.name);
    }

    public void SetBet(int seat, int amount)
    {
        if (!ValidSeat(seat))
            return;

        // Replace the temporary animated bundle with the authoritative Python bet.
        ClearAnimatedActionChips(seat);

        Transform anchor = GetBetAnchor(seat);
        if (anchor == null)
        {
            Debug.LogWarning("ChipManager: no bet anchor for seat " + seat);
            return;
        }

        RebuildAmount(
            betObjects[seat],
            anchor,
            Mathf.Max(0, amount),
            "Bet"
        );

        Debug.Log("[ChipManager] BET seat=" + seat + " amount=" + amount + " anchor=" + anchor.name);
    }

    public void SetPot(int amount)
    {
        int safeAmount = Mathf.Max(0, amount);

        if (potAnchor == null)
        {
            Debug.LogWarning("ChipManager: Pot Anchor is not assigned.");
            return;
        }

        // Do not destroy chips while they are visibly flying to the pot.
        if (collectingBets)
        {
            queuedPotAmount = safeAmount;
            Debug.Log("[ChipManager] POT queued during collect: " + safeAmount);
            return;
        }

        RebuildAmount(
            potObjects,
            potAnchor,
            safeAmount,
            "Pot"
        );

        Debug.Log("[ChipManager] POT amount=" + safeAmount);
    }

    // =========================================================
    // BET ANCHORS -> POT ANCHOR
    // Call this at the end of each betting street.
    // =========================================================

    public void CollectBetsToPot()
    {
        if (potAnchor == null)
        {
            Debug.LogWarning("[ChipManager] Cannot collect bets: PotAnchor missing.");
            return;
        }

        if (collectingBets)
        {
            Debug.Log("[ChipManager] CollectBetsToPot ignored - already collecting.");
            return;
        }

        if (awardRoutine != null)
        {
            Debug.LogWarning("[ChipManager] Cannot collect bets while pot is being awarded.");
            return;
        }

        collectRoutine = StartCoroutine(CollectBetsToPotRoutine());
    }

    private IEnumerator CollectBetsToPotRoutine()
    {
        collectingBets = true;

        List<GameObject> moving = new List<GameObject>();

        // Transfer ownership of the bet visuals to this routine WITHOUT destroying them.
        for (int seat = 0; seat < 4; seat++)
        {
            List<GameObject> seatBets = betObjects[seat];

            for (int i = 0; i < seatBets.Count; i++)
            {
                if (seatBets[i] != null)
                    moving.Add(seatBets[i]);
            }

            seatBets.Clear();
            ClearAnimatedActionChips(seat);
        }

        if (moving.Count == 0)
        {
            collectingBets = false;
            collectRoutine = null;

            ApplyQueuedPotIfNeeded();
            yield break;
        }

        int existingPotVisualCount = potObjects.Count;

        // Start every chip with a tiny stagger so the move reads better visually.
        for (int i = 0; i < moving.Count; i++)
        {
            GameObject chip = moving[i];
            if (chip == null)
                continue;

            Vector3 targetPosition = GetWorldPositionForVisualIndex(
                potAnchor,
                existingPotVisualCount + i
            );

            StartCoroutine(
                MoveChipRoutine(
                    chip.transform,
                    targetPosition,
                    potAnchor.rotation,
                    betToPotDuration,
                    i * Mathf.Max(0f, chipMoveStagger)
                )
            );
        }

        float totalWait =
            Mathf.Max(0.01f, betToPotDuration) +
            Mathf.Max(0f, chipMoveStagger) * Mathf.Max(0, moving.Count - 1);

        yield return new WaitForSeconds(totalWait);

        for (int i = 0; i < moving.Count; i++)
        {
            if (moving[i] != null)
                potObjects.Add(moving[i]);
        }

        collectingBets = false;
        collectRoutine = null;

        Debug.Log("[ChipManager] Bets -> Pot finished. Visual chips in pot=" + potObjects.Count);

        // If Python sent the real pot amount during the animation, now replace
        // the moved visual bundle with the exact authoritative denomination layout.
        ApplyQueuedPotIfNeeded();
    }

    private void ApplyQueuedPotIfNeeded()
    {
        if (queuedPotAmount < 0 || potAnchor == null)
            return;

        int amount = queuedPotAmount;
        queuedPotAmount = -1;

        RebuildAmount(
            potObjects,
            potAnchor,
            amount,
            "Pot"
        );

        Debug.Log("[ChipManager] Applied queued authoritative POT=" + amount);
    }

    // =========================================================
    // POT -> WINNER STACK
    // Call this when Python tells Unity who won the hand.
    // =========================================================

    public void AwardPotToWinner(int winnerSeat)
    {
        if (!ValidSeat(winnerSeat))
            return;

        if (awardRoutine != null)
        {
            Debug.Log("[ChipManager] AwardPotToWinner ignored - already awarding.");
            return;
        }

        awardRoutine = StartCoroutine(AwardPotToWinnerRoutine(winnerSeat));
    }

    private IEnumerator AwardPotToWinnerRoutine(int winnerSeat)
    {
        awardingPot = true;

        // If the final street still has chips on BetAnchors, collect them first.
        if (HasAnyBetObjects())
        {
            if (!collectingBets)
                CollectBetsToPot();

            while (collectingBets)
                yield return null;
        }

        Transform winnerAnchor = GetStackAnchor(winnerSeat);
        if (winnerAnchor == null)
        {
            Debug.LogWarning("[ChipManager] Winner stack anchor missing for seat " + winnerSeat);
            awardingPot = false;
            awardRoutine = null;
            yield break;
        }

        List<GameObject> moving = new List<GameObject>(potObjects);
        potObjects.Clear();

        if (moving.Count == 0)
        {
            Debug.Log("[ChipManager] AwardPotToWinner: no pot visuals to move.");
            awardingPot = false;
            awardRoutine = null;
            yield break;
        }

        // Put incoming chips after the player's currently rendered stack,
        // so they visually merge into the stack instead of one exact point.
        int existingStackVisualCount = stackObjects[winnerSeat].Count;

        for (int i = 0; i < moving.Count; i++)
        {
            GameObject chip = moving[i];
            if (chip == null)
                continue;

            Vector3 targetPosition = GetWorldPositionForVisualIndex(
                winnerAnchor,
                existingStackVisualCount + i
            );

            StartCoroutine(
                MoveChipRoutine(
                    chip.transform,
                    targetPosition,
                    winnerAnchor.rotation,
                    potToWinnerDuration,
                    i * Mathf.Max(0f, chipMoveStagger)
                )
            );
        }

        float totalWait =
            Mathf.Max(0.01f, potToWinnerDuration) +
            Mathf.Max(0f, chipMoveStagger) * Mathf.Max(0, moving.Count - 1);

        yield return new WaitForSeconds(totalWait);

        // These are transit visuals only. The real winner stack is rebuilt by
        // the next authoritative Python SetStack(...) message.
        for (int i = 0; i < moving.Count; i++)
        {
            if (moving[i] != null)
                Destroy(moving[i]);
        }

        awardingPot = false;
        awardRoutine = null;

        Debug.Log("[ChipManager] POT -> WINNER seat=" + winnerSeat + " finished");
    }

    // =========================================================
    // TEMPORARY CALL / RAISE BUNDLE
    // =========================================================

    // Creates a temporary bundle from the Python action amount.
    // AnchorHold moves this whole root with the fly hand during CALL/RAISE.
    public GameObject CreateAnimatedActionChips(int seat, int amount)
    {
        if (!ValidSeat(seat) || amount <= 0)
            return null;

        Transform stackAnchor = GetStackAnchor(seat);
        if (stackAnchor == null || chipPrefab == null)
            return null;

        ClearAnimatedActionChips(seat);

        GameObject root = new GameObject("AnimatedActionChips_Seat" + seat);

        // Keep the animated bundle in world space. This avoids inheriting any
        // accidental scale from a fly/anchor hierarchy.
        root.transform.position = stackAnchor.position;
        root.transform.rotation = stackAnchor.rotation;
        root.transform.localScale = Vector3.one;

        BuildAmountUnderRoot(root.transform, amount, "Animated");
        animatedActionRoots[seat] = root;

        return root;
    }

    public void ClearAnimatedActionChips(int seat)
    {
        if (!ValidSeat(seat))
            return;

        GameObject root = animatedActionRoots[seat];
        if (root != null)
            Destroy(root);

        animatedActionRoots[seat] = null;
    }

    // =========================================================
    // CHIP MOVEMENT
    // =========================================================

    private IEnumerator MoveChipRoutine(
        Transform chip,
        Vector3 targetPosition,
        Quaternion targetRotation,
        float duration,
        float startDelay
    )
    {
        if (chip == null)
            yield break;

        if (startDelay > 0f)
            yield return new WaitForSeconds(startDelay);

        if (chip == null)
            yield break;

        Rigidbody rb = chip.GetComponent<Rigidbody>();
        if (rb != null)
        {
            rb.isKinematic = true;
            rb.useGravity = false;
        }

        Vector3 startPosition = chip.position;
        Quaternion startRotation = chip.rotation;

        float safeDuration = Mathf.Max(0.01f, duration);
        float elapsed = 0f;

        while (elapsed < safeDuration && chip != null)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / safeDuration);

            // SmoothStep.
            float eased = t * t * (3f - 2f * t);

            Vector3 position = Vector3.Lerp(
                startPosition,
                targetPosition,
                eased
            );

            // Small arc - chips lift slightly above the table while moving.
            position += Vector3.up * Mathf.Sin(t * Mathf.PI) * moveArcHeight;

            chip.position = position;
            chip.rotation = Quaternion.Slerp(
                startRotation,
                targetRotation,
                eased
            );

            yield return null;
        }

        if (chip != null)
        {
            chip.position = targetPosition;
            chip.rotation = targetRotation;
        }
    }

    private bool HasAnyBetObjects()
    {
        for (int seat = 0; seat < 4; seat++)
        {
            if (betObjects[seat].Count > 0)
                return true;
        }

        return false;
    }

    private Vector3 GetWorldPositionForVisualIndex(
        Transform anchor,
        int visualIndex
    )
    {
        int column = visualIndex / Mathf.Max(1, maxPerColumn);
        int level = visualIndex % Mathf.Max(1, maxPerColumn);

        Vector3 localOffset = new Vector3(
            column * columnSpacing,
            level * chipHeight,
            0f
        );

        return anchor.TransformPoint(localOffset);
    }

    // =========================================================
    // BUILD / REBUILD CHIP AMOUNTS
    // =========================================================

    private void RebuildAmount(
        List<GameObject> objects,
        Transform anchor,
        int amount,
        string groupName
    )
    {
        ClearList(objects);

        if (amount <= 0)
            return;

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
                GameObject chip = CreateOneChip(
                    anchor,
                    denomination,
                    visualIndex,
                    groupName
                );

                objects.Add(chip);
                visualIndex++;
            }
        }
    }

    private void BuildAmountUnderRoot(
        Transform root,
        int amount,
        string groupName
    )
    {
        int remaining = amount;
        int visualIndex = 0;

        foreach (int denomination in Denominations)
        {
            int count = remaining / denomination;
            remaining %= denomination;

            for (int i = 0; i < count; i++)
            {
                CreateOneChip(root, denomination, visualIndex, groupName);
                visualIndex++;
            }
        }
    }

    private GameObject CreateOneChip(
        Transform anchor,
        int denomination,
        int visualIndex,
        string groupName
    )
    {
        int column = visualIndex / Mathf.Max(1, maxPerColumn);
        int level = visualIndex % Mathf.Max(1, maxPerColumn);

        Vector3 localOffset = new Vector3(
            column * columnSpacing,
            level * chipHeight,
            0f
        );

        GameObject chip;

        // Animated bundles deliberately parent chips under an unscaled runtime
        // root so AnchorHold can move the whole bundle. Static stack/bet/pot
        // anchors may live under scaled scene objects, so place those chips in
        // world space instead of inheriting the parent scale.
        if (anchor.name.StartsWith("AnimatedActionChips_"))
        {
            chip = Instantiate(chipPrefab, anchor);
            chip.transform.localPosition = localOffset;
            chip.transform.localRotation = Quaternion.identity;
            chip.transform.localScale = chipPrefab.transform.localScale;
        }
        else
        {
            chip = Instantiate(chipPrefab);
            chip.transform.position = anchor.TransformPoint(localOffset);
            chip.transform.rotation = anchor.rotation;
            chip.transform.localScale = chipPrefab.transform.localScale;
        }

        chip.name = groupName + "_Chip_" + denomination;

        Renderer renderer = chip.GetComponentInChildren<Renderer>();
        if (renderer != null)
            renderer.material.color = ColorForDenomination(denomination);

        Rigidbody rb = chip.GetComponent<Rigidbody>();
        if (rb != null)
        {
            rb.isKinematic = true;
            rb.useGravity = false;
        }

        return chip;
    }

    // =========================================================
    // HELPERS
    // =========================================================

    private bool ValidSeat(int seat)
    {
        if (seat >= 0 && seat < 4)
            return true;

        Debug.LogError("ChipManager: invalid seat " + seat);
        return false;
    }

    private Transform GetStackAnchor(int seat)
    {
        switch (seat)
        {
            case 0: return player1Stack;
            case 1: return player2Stack;
            case 2: return player3Stack;
            case 3: return player4Stack;
            default: return null;
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
            default: return null;
        }
    }

    private Color ColorForDenomination(int denomination)
    {
        switch (denomination)
        {
            case 500: return new Color(0.12f, 0.12f, 0.12f);
            case 100: return new Color(0.08f, 0.22f, 0.70f);
            case 25:  return new Color(0.08f, 0.55f, 0.20f);
            case 5:   return new Color(0.75f, 0.08f, 0.08f);
            default:  return new Color(0.90f, 0.90f, 0.90f);
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

    private void AutoAssignMissingAnchors()
    {
        for (int seat = 0; seat < 4; seat++)
        {
            GameObject fly = GameObject.Find("Fly" + (seat + 1));
            if (fly == null)
                continue;

            Transform stack = FindChildStartingWith(fly.transform, "ChipAnchors");
            Transform bet = FindChildStartingWith(fly.transform, "BetAnchors");

            switch (seat)
            {
                case 0:
                    if (player1Stack == null) player1Stack = stack;
                    if (player1Bet == null) player1Bet = bet;
                    break;

                case 1:
                    if (player2Stack == null) player2Stack = stack;
                    if (player2Bet == null) player2Bet = bet;
                    break;

                case 2:
                    if (player3Stack == null) player3Stack = stack;
                    if (player3Bet == null) player3Bet = bet;
                    break;

                case 3:
                    if (player4Stack == null) player4Stack = stack;
                    if (player4Bet == null) player4Bet = bet;
                    break;
            }
        }

        if (potAnchor == null)
        {
            // Keep your existing misspelled scene name for compatibility.
            GameObject pot = GameObject.Find("PotArchorn");

            // Also support the correctly-spelled variants if you rename it later.
            if (pot == null)
                pot = GameObject.Find("PotAnchor");

            if (pot == null)
                pot = GameObject.Find("PotAnchorn");

            if (pot != null)
                potAnchor = pot.transform;
        }
    }

    private Transform FindChildStartingWith(Transform root, string prefix)
    {
        foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
        {
            if (child.name.StartsWith(prefix, System.StringComparison.OrdinalIgnoreCase))
                return child;
        }

        return null;
    }
}
