using UnityEngine;

public class CardManager : MonoBehaviour
{
    [Header("Card Prefab")]
    public GameObject cardPrefab;

    [Header("Fly 1")]
    public Transform fly1Card1;
    public Transform fly1Card2;

    [Header("Fly 2")]
    public Transform fly2Card1;
    public Transform fly2Card2;

    [Header("Fly 3")]
    public Transform fly3Card1;
    public Transform fly3Card2;

    [Header("Fly 4")]
    public Transform fly4Card1;
    public Transform fly4Card2;

    [Header("Board")]
    public Transform boardCard1;
    public Transform boardCard2;
    public Transform boardCard3;
    public Transform boardCard4;
    public Transform boardCard5;

    [Header("Hole-card visual")]
    [Tooltip("World-scale multiplier. Keep at 1 unless cards are too large/small.")]
    public float holeCardScaleMultiplier = 1.0f;

    [Header("Fold integration")]
    [Tooltip("Automatically finds/adds FoldCardController on each fly Animator object.")]
    public bool autoSetupFoldControllers = true;

    private readonly GameObject[,] holeCardObjects = new GameObject[4, 2];
    private readonly GameObject[] boardCardObjects = new GameObject[5];

    // TRUE = CardManager keeps the card attached to Card1/Card2 anchor.
    // FALSE = FoldCardController/physics owns the card.
    private readonly bool[,] followHoleCardAnchor = new bool[4, 2];

    // Once a fly starts folding, NO script may reattach those same cards
    // to Card1/Card2 until the next hand deals new cards.
    private readonly bool[] foldLockedSeats = new bool[4];

    private readonly FoldCardController[] foldControllers =
        new FoldCardController[4];

    private void Awake()
    {
        ResetFollowStates();
        AutoAssignMissingAnchors();

        if (autoSetupFoldControllers)
            AutoSetupFoldControllers();
    }

    private void LateUpdate()
    {
        // Hole cards normally follow Card1/Card2 in WORLD SPACE.
        // During FOLD, FoldCardController disables this follow so it can move
        // the real cards with the hand and then release them to physics.
        for (int seat = 0; seat < 4; seat++)
        {
            for (int i = 0; i < 2; i++)
            {
                if (!followHoleCardAnchor[seat, i])
                    continue;

                GameObject card = holeCardObjects[seat, i];
                Transform slot = GetHoleSlot(seat, i);

                if (card == null || slot == null)
                    continue;

                card.transform.position = slot.position;
                card.transform.rotation = slot.rotation;
            }
        }
    }

    // =========================================================
    // NEW HAND
    // =========================================================

    public void NewHand()
    {
        // Fold controllers can still hold references to cards thrown in the
        // previous hand, so clear them before destroying the objects.
        for (int seat = 0; seat < 4; seat++)
        {
            FoldCardController fold = GetFoldController(seat);
            if (fold != null)
                fold.ClearCards();
        }

        for (int seat = 0; seat < 4; seat++)
        {
            foldLockedSeats[seat] = false;

            for (int card = 0; card < 2; card++)
            {
                if (holeCardObjects[seat, card] != null)
                    Destroy(holeCardObjects[seat, card]);

                holeCardObjects[seat, card] = null;
                followHoleCardAnchor[seat, card] = true;
            }
        }

        for (int i = 0; i < 5; i++)
        {
            if (boardCardObjects[i] != null)
                Destroy(boardCardObjects[i]);

            boardCardObjects[i] = null;
        }

        Debug.Log("[CardManager] NEW HAND - all cards cleared");
    }

    // =========================================================
    // HOLE CARDS
    // =========================================================

    public void SetHoleCards(int seat, string[] cards)
    {
        if (seat < 0 || seat > 3)
            return;

        if (cards == null || cards.Length < 2)
            return;

        Transform card1Slot = GetHoleSlot(seat, 0);
        Transform card2Slot = GetHoleSlot(seat, 1);

        if (card1Slot == null || card2Slot == null)
        {
            Debug.LogWarning("[CardManager] missing card anchors for seat " + seat);

            AutoAssignMissingAnchors();

            card1Slot = GetHoleSlot(seat, 0);
            card2Slot = GetHoleSlot(seat, 1);
        }

        if (card1Slot == null || card2Slot == null)
        {
            Debug.LogError("[CardManager] STILL missing card anchors for seat " + seat);
            return;
        }

        FoldCardController oldFold = GetFoldController(seat);
        if (oldFold != null)
            oldFold.ClearCards();

        // Unlock ONLY when a NEW pair of hole cards is dealt.
        foldLockedSeats[seat] = false;

        for (int i = 0; i < 2; i++)
        {
            if (holeCardObjects[seat, i] != null)
                Destroy(holeCardObjects[seat, i]);

            holeCardObjects[seat, i] = null;
            followHoleCardAnchor[seat, i] = true;
        }

        holeCardObjects[seat, 0] =
            CreateWorldCard(cards[0], card1Slot, true);

        holeCardObjects[seat, 1] =
            CreateWorldCard(cards[1], card2Slot, true);

        FoldCardController fold = GetFoldController(seat);

        if (fold == null && autoSetupFoldControllers)
        {
            AutoSetupFoldController(seat);
            fold = GetFoldController(seat);
        }

        if (fold != null)
        {
            fold.SetSeatAndCardManager(seat, this);

            fold.SetCards(
                holeCardObjects[seat, 0],
                holeCardObjects[seat, 1]
            );
        }

        Debug.Log(
            "[CardManager] SEAT " + seat +
            " CARDS: " + cards[0] + " " + cards[1] +
            " | anchorScale=" + card1Slot.lossyScale +
            " | foldController=" + (fold != null)
        );
    }

    /// <summary>
    /// Called by FoldCardController when the animation grabs the cards.
    /// FALSE means CardManager stops snapping the cards back to Card1/Card2.
    /// </summary>
    public void SetHoleCardsFollowAnchors(int seat, bool follow)
    {
        if (seat < 0 || seat > 3)
            return;

        // Safety: do not let a folded card suddenly snap back to the hand.
        if (follow && foldLockedSeats[seat])
        {
            Debug.LogWarning(
                "[CardManager] BLOCKED reattaching folded cards for seat=" + seat
            );
            return;
        }

        followHoleCardAnchor[seat, 0] = follow;
        followHoleCardAnchor[seat, 1] = follow;

        Debug.Log(
            "[CardManager] seat=" + seat +
            " followHoleCards=" + follow
        );
    }

    // Called at PickUpCards AND ThrowCards, even if an animation event was missed.
    public void DetachHoleCardsForFold(int seat)
    {
        if (seat < 0 || seat > 3)
            return;

        foldLockedSeats[seat] = true;
        followHoleCardAnchor[seat, 0] = false;
        followHoleCardAnchor[seat, 1] = false;

        Debug.Log("[CardManager] seat=" + seat + " FOLD LOCK: detached from hand");
    }

    /// <summary>
    /// Useful if another script wants to query the actual spawned cards.
    /// </summary>
    public GameObject GetHoleCardObject(int seat, int cardIndex)
    {
        if (seat < 0 || seat > 3)
            return null;

        if (cardIndex < 0 || cardIndex > 1)
            return null;

        return holeCardObjects[seat, cardIndex];
    }

    // =========================================================
    // BOARD
    // =========================================================

    public void SetBoard(string[] cards)
    {
        if (cards == null)
            return;

        Transform[] slots =
        {
            boardCard1,
            boardCard2,
            boardCard3,
            boardCard4,
            boardCard5
        };

        int count = Mathf.Min(cards.Length, 5);

        for (int i = 0; i < count; i++)
        {
            if (slots[i] == null)
                continue;

            if (boardCardObjects[i] != null)
                continue;

            boardCardObjects[i] =
                CreateWorldCard(cards[i], slots[i], false);
        }
    }

    // =========================================================
    // CARD CREATION
    // =========================================================

    private GameObject CreateWorldCard(
        string cardName,
        Transform target,
        bool holeCard
    )
    {
        if (cardPrefab == null)
        {
            Debug.LogError("[CardManager] Card Prefab is not assigned.");
            return null;
        }

        if (target == null)
            return null;

        string normalized =
            (cardName ?? "").Trim().ToUpperInvariant();

        // Hole-card anchors are under an extremely small scaled fly hierarchy,
        // so cards are intentionally spawned in WORLD SPACE.
        GameObject card = Instantiate(cardPrefab);

        card.transform.position = target.position;
        card.transform.rotation = target.rotation;

        Vector3 prefabScale = cardPrefab.transform.localScale;

        float mul =
            holeCard
                ? Mathf.Max(0.0001f, holeCardScaleMultiplier)
                : 1.0f;

        card.transform.localScale = prefabScale * mul;

        card.name =
            (holeCard ? "HoleCard_" : "BoardCard_") +
            normalized;

        // Hole cards must stay static until a FOLD animation takes control.
        if (holeCard)
        {
            Rigidbody rb = card.GetComponent<Rigidbody>();

            if (rb != null)
            {
#if UNITY_6000_0_OR_NEWER
                rb.linearVelocity = Vector3.zero;
#else
                rb.velocity = Vector3.zero;
#endif
                rb.angularVelocity = Vector3.zero;
                rb.useGravity = false;
                rb.isKinematic = true;
            }
        }

        Texture2D texture =
            Resources.Load<Texture2D>(
                "cards/" + normalized
            );

        if (texture == null)
        {
            Debug.LogError(
                "Missing card texture: Resources/cards/" +
                normalized
            );

            return card;
        }

        Renderer renderer =
            card.GetComponentInChildren<Renderer>();

        if (renderer == null)
        {
            Debug.LogError("PokerCard has no Renderer.");
            return card;
        }

        Material material =
            new Material(renderer.material);

        if (material.HasProperty("_BaseMap"))
            material.SetTexture("_BaseMap", texture);

        if (material.HasProperty("_MainTex"))
            material.SetTexture("_MainTex", texture);

        renderer.material = material;

        return card;
    }

    // =========================================================
    // FOLD CONTROLLER SETUP
    // =========================================================

    private FoldCardController GetFoldController(int seat)
    {
        if (seat < 0 || seat > 3)
            return null;

        if (foldControllers[seat] == null && autoSetupFoldControllers)
            AutoSetupFoldController(seat);

        return foldControllers[seat];
    }

    private void AutoSetupFoldControllers()
    {
        for (int seat = 0; seat < 4; seat++)
            AutoSetupFoldController(seat);
    }

    private void AutoSetupFoldController(int seat)
    {
        if (seat < 0 || seat > 3)
            return;

        GameObject fly =
            GameObject.Find("Fly" + (seat + 1));

        if (fly == null)
            return;

        // Animation Events are delivered to components on the same GameObject
        // as the Animator, so FoldCardController belongs there.
        Animator animator =
            fly.GetComponentInChildren<Animator>(true);

        GameObject controllerObject =
            animator != null
                ? animator.gameObject
                : fly;

        FoldCardController fold =
            controllerObject.GetComponent<FoldCardController>();

        if (fold == null)
            fold = controllerObject.AddComponent<FoldCardController>();

        fold.SetSeatAndCardManager(seat, this);

        if (fold.handAnchor == null)
        {
            Transform hand =
                FindChildStartingWith(
                    fly.transform,
                    "HandAnchor"
                );

            // Your current rig also used the spelling "HandAnchorn",
            // which is still caught by StartsWith("HandAnchor").
            if (hand == null)
            {
                hand =
                    FindDeepChild(
                        fly.transform,
                        "tarsal_claw_T1_left"
                    );
            }

            fold.handAnchor = hand;
        }

        if (fold.foldTarget == null)
        {
            GameObject target =
                GameObject.Find(
                    "FoldAnchor" + (seat + 1)
                );

            if (target == null)
                target = GameObject.Find("FoldAnchor");

            // Safe fallback: throw toward the middle of the table.
            if (target == null)
                target = GameObject.Find("PotArchorn");

            if (target == null)
                target = GameObject.Find("PotAnchor");

            if (target != null)
                fold.foldTarget = target.transform;
        }

        foldControllers[seat] = fold;

        Debug.Log(
            "[CardManager] FOLD seat=" + seat +
            " controller=" + fold.name +
            " hand=" +
            (fold.handAnchor != null
                ? fold.handAnchor.name
                : "NULL") +
            " target=" +
            (fold.foldTarget != null
                ? fold.foldTarget.name
                : "NULL")
        );
    }

    // =========================================================
    // ANCHORS
    // =========================================================

    private Transform GetHoleSlot(int seat, int card)
    {
        switch (seat)
        {
            case 0:
                return card == 0
                    ? fly1Card1
                    : fly1Card2;

            case 1:
                return card == 0
                    ? fly2Card1
                    : fly2Card2;

            case 2:
                return card == 0
                    ? fly3Card1
                    : fly3Card2;

            case 3:
                return card == 0
                    ? fly4Card1
                    : fly4Card2;

            default:
                return null;
        }
    }

    private void AutoAssignMissingAnchors()
    {
        for (int seat = 0; seat < 4; seat++)
        {
            GameObject fly =
                GameObject.Find(
                    "Fly" + (seat + 1)
                );

            if (fly == null)
                continue;

            Transform cardsHeld =
                FindDeepChild(
                    fly.transform,
                    "CardsHeld"
                );

            Transform c1 =
                cardsHeld != null
                    ? FindDirectChild(
                        cardsHeld,
                        "Card1"
                    )
                    : null;

            Transform c2 =
                cardsHeld != null
                    ? FindDirectChild(
                        cardsHeld,
                        "Card2"
                    )
                    : null;

            switch (seat)
            {
                case 0:
                    if (fly1Card1 == null)
                        fly1Card1 = c1;

                    if (fly1Card2 == null)
                        fly1Card2 = c2;

                    break;

                case 1:
                    if (fly2Card1 == null)
                        fly2Card1 = c1;

                    if (fly2Card2 == null)
                        fly2Card2 = c2;

                    break;

                case 2:
                    if (fly3Card1 == null)
                        fly3Card1 = c1;

                    if (fly3Card2 == null)
                        fly3Card2 = c2;

                    break;

                case 3:
                    if (fly4Card1 == null)
                        fly4Card1 = c1;

                    if (fly4Card2 == null)
                        fly4Card2 = c2;

                    break;
            }
        }

        GameObject board =
            GameObject.Find("BOARD");

        if (board != null)
        {
            if (boardCard1 == null)
                boardCard1 =
                    FindDirectChild(
                        board.transform,
                        "Card1"
                    );

            if (boardCard2 == null)
                boardCard2 =
                    FindDirectChild(
                        board.transform,
                        "Card2"
                    );

            if (boardCard3 == null)
                boardCard3 =
                    FindDirectChild(
                        board.transform,
                        "Card3"
                    );

            if (boardCard4 == null)
                boardCard4 =
                    FindDirectChild(
                        board.transform,
                        "Card4"
                    );

            if (boardCard5 == null)
                boardCard5 =
                    FindDirectChild(
                        board.transform,
                        "Card5"
                    );
        }
    }

    private void ResetFollowStates()
    {
        for (int seat = 0; seat < 4; seat++)
        {
            followHoleCardAnchor[seat, 0] = true;
            followHoleCardAnchor[seat, 1] = true;
        }
    }

    private Transform FindDeepChild(
        Transform root,
        string exactName
    )
    {
        if (root == null)
            return null;

        foreach (
            Transform child
            in root.GetComponentsInChildren<Transform>(true)
        )
        {
            if (child.name == exactName)
                return child;
        }

        return null;
    }

    private Transform FindChildStartingWith(
        Transform root,
        string prefix
    )
    {
        if (root == null)
            return null;

        foreach (
            Transform child
            in root.GetComponentsInChildren<Transform>(true)
        )
        {
            if (
                child.name.StartsWith(
                    prefix,
                    System.StringComparison.OrdinalIgnoreCase
                )
            )
            {
                return child;
            }
        }

        return null;
    }

    private Transform FindDirectChild(
        Transform root,
        string exactName
    )
    {
        if (root == null)
            return null;

        for (int i = 0; i < root.childCount; i++)
        {
            Transform child = root.GetChild(i);

            if (child.name == exactName)
                return child;
        }

        return null;
    }
}
