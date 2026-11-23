using System.Collections;
using UnityEngine;

/// <summary>
/// Controls cards during FOLD.
///
/// Animation Events:
/// 1. PickUpCards()       - when the fly hand reaches the cards.
/// 2. ThrowCards()        - when the hand releases the cards.
/// 3. AnimationFinished() - remains handled by FlyAnimationController.
///
/// IMPORTANT:
/// This version DOES NOT use Rigidbody for the throw.
/// The cards follow a short scripted arc, rotate, land at FoldTarget,
/// and then STOP there until CardManager clears them on a new hand.
/// </summary>
public class FoldCardController : MonoBehaviour
{
    [Header("Runtime")]
    [Range(0, 3)]
    public int seat = 0;

    public CardManager cardManager;

    [Header("References")]
    [Tooltip("Anchor following the fly hand/claw.")]
    public Transform handAnchor;

    [Tooltip("Point on the table where folded cards should land.")]
    public Transform foldTarget;

    [Header("Current hole cards")]
    public Transform card1;
    public Transform card2;

    [Header("Cards while held")]
    public Vector3 card1HandOffset =
        new Vector3(-0.01f, 0f, 0f);

    public Vector3 card2HandOffset =
        new Vector3(0.01f, 0f, 0f);

    [Tooltip("Extra rotation while the cards are held by the hand.")]
    public Vector3 heldEulerOffset = Vector3.zero;

    [Header("Scripted throw")]
    [Tooltip("How long the throw lasts.")]
    public float throwDuration = 4f;

    [Tooltip("Height of the throw arc.")]
    public float throwArcHeight = 0.08f;

    [Tooltip("How far the two cards separate from each other when landing.")]
    public float landingSideSpacing = 0.035f;

    [Tooltip("Small random offset on the table so both cards do not land perfectly.")]
    public float randomLandingOffset = 0.012f;

    [Tooltip("Minimum full rotations during the throw.")]
    public float minRotationTurns = 0.55f;

    [Tooltip("Maximum full rotations during the throw.")]
    public float maxRotationTurns = 1.10f;

    [Tooltip("Extra Y offset above FoldTarget. Useful if cards clip into the table.")]
    public float landingHeightOffset = 0.003f;

    [Tooltip("How far in front of FoldTarget the cards land.")]
    public float landingForwardOffset = 0.09f;

    [Header("Landing rotation")]
    [Tooltip("Rotation relative to FoldTarget after the card lands.")]
    public Vector3 landingEulerOffset = Vector3.zero;

    [Tooltip("Random yaw added when the card lands.")]
    public float randomLandingYaw = 12f;

    [Header("Debug")]
    public bool debugLogs = true;

    private bool holdingCards = false;
    private bool cardsThrown = false;

    private Coroutine card1ThrowRoutine;
    private Coroutine card2ThrowRoutine;
    private int activeThrowCount = 0;

    // Thrown card visuals are clones detached from CardManager and Animator.
    // CardManager may keep moving original cards, but these copies will not snap back.
    private Transform thrownCard1;
    private Transform thrownCard2;

    public bool HasCards => card1 != null || card2 != null;
    public bool HasReleasedCards => cardsThrown;
    public bool IsThrowInProgress => activeThrowCount > 0;

    // Unity does not overwrite Inspector-serialized fields when code defaults
    // change. Use this context-menu command on an existing component.
    [ContextMenu("Apply screenshot defaults")]
    private void ApplyScreenshotDefaults()
    {
        card1HandOffset = new Vector3(-0.01f, 0f, 0f);
        card2HandOffset = new Vector3(0.01f, 0f, 0f);
        heldEulerOffset = Vector3.zero;
        throwDuration = 4f;
        throwArcHeight = 0.08f;
        landingSideSpacing = 0.035f;
        randomLandingOffset = 0.012f;
        minRotationTurns = 0.55f;
        maxRotationTurns = 1.10f;
        landingHeightOffset = 0.003f;
        landingForwardOffset = 0.09f;
        landingEulerOffset = Vector3.zero;
        randomLandingYaw = 12f;
        debugLogs = true;
    }

    private void Reset()
    {
        ApplyScreenshotDefaults();
    }

    private void LateUpdate()
    {
        if (!holdingCards || handAnchor == null)
            return;

        FollowHand(card1, card1HandOffset);
        FollowHand(card2, card2HandOffset);
    }


    // =========================================================
    // SETUP
    // =========================================================

    public void SetSeatAndCardManager(
        int newSeat,
        CardManager manager
    )
    {
        seat = Mathf.Clamp(newSeat, 0, 3);
        cardManager = manager;
    }


    public void SetCards(
        GameObject firstCard,
        GameObject secondCard
    )
    {
        SetCards(
            firstCard != null
                ? firstCard.transform
                : null,

            secondCard != null
                ? secondCard.transform
                : null
        );
    }


    public void SetCards(
        Transform firstCard,
        Transform secondCard
    )
    {
        StopThrowCoroutines();
        ClearThrownVisuals();

        holdingCards = false;
        cardsThrown = false;

        card1 = firstCard;
        card2 = secondCard;

        MakeCardStatic(card1);
        MakeCardStatic(card2);

        // New cards are again controlled by CardManager anchors.
        cardManager?.SetHoleCardsFollowAnchors(
            seat,
            true
        );

        if (debugLogs)
        {
            Debug.Log(
                "[FoldCardController] seat=" + seat +
                " cards assigned | card1=" +
                (card1 != null ? card1.name : "NULL") +
                " card2=" +
                (card2 != null ? card2.name : "NULL")
            );
        }
    }


    public void ClearCards()
    {
        StopThrowCoroutines();
        ClearThrownVisuals();

        holdingCards = false;
        cardsThrown = false;

        card1 = null;
        card2 = null;
    }


    // =========================================================
    // ANIMATION EVENT 1 - PICK UP
    // =========================================================

    public void PickUpCards()
    {
        // IMPORTANT: Unity Animation Events can fire again because a clip is
        // looped or crossfaded. Never allow a second grab to cancel a throw.
        // The lock is reset only by SetCards() for the next hand.
        if (cardsThrown || activeThrowCount > 0)
        {
            Debug.LogWarning(
                "[FOLD V29] seat=" + seat +
                " IGNORED duplicate PickUpCards AFTER THROW. " +
                "Check Fly_Fold clip: Loop Time must be OFF."
            );
            return;
        }

        if (holdingCards)
        {
            if (debugLogs)
                Debug.Log("[FOLD V29] seat=" + seat + " ignored repeated PickUpCards while holding");
            return;
        }

        if (handAnchor == null)
        {
            Debug.LogError(
                "[FoldCardController] seat=" + seat +
                " HandAnchor is NULL."
            );

            return;
        }

        if (card1 == null && card2 == null)
        {
            Debug.LogWarning(
                "[FoldCardController] seat=" + seat +
                " has no cards to pick up."
            );

            return;
        }

        StopThrowCoroutines();

        // CardManager must stop forcing the cards back to Card1/Card2.
        EnsureDetachedFromHand();

        cardsThrown = false;
        holdingCards = true;

        MakeCardStatic(card1);
        MakeCardStatic(card2);

        // Snap them to the hand immediately on the animation-event frame.
        FollowHand(card1, card1HandOffset);
        FollowHand(card2, card2HandOffset);

        if (debugLogs)
        {
            Debug.Log(
                "[FOLD] seat=" + seat +
                " picked up cards"
            );
        }
    }


    // =========================================================
    // ANIMATION EVENT 2 - THROW / RELEASE
    // =========================================================

    public void ThrowCards()
    {
        if (cardsThrown)
        {
            if (debugLogs)
                Debug.Log("[FOLD V29] seat=" + seat + " ignored duplicate ThrowCards");
            return;
        }

        if (foldTarget == null)
            TryFindFoldTarget();

        if (foldTarget == null)
        {
            Debug.LogError(
                "[FoldCardController] seat=" + seat +
                " FoldTarget is NULL. No throw possible."
            );
            return;
        }

        // The true cards still belong to CardManager. Lock them and launch
        // separate world-space visual copies, so another script/Animator
        // can NEVER pull the visible thrown cards back to the fly.
        EnsureDetachedFromHand();
        holdingCards = false;
        cardsThrown = true;

        ClearThrownVisuals();
        thrownCard1 = SpawnThrowVisual(card1, 1);
        thrownCard2 = SpawnThrowVisual(card2, 2);

        activeThrowCount =
            (thrownCard1 != null ? 1 : 0) +
            (thrownCard2 != null ? 1 : 0);

        if (thrownCard1 != null)
            card1ThrowRoutine = StartCoroutine(AnimateThrow(thrownCard1, -1f, 0));

        if (thrownCard2 != null)
            card2ThrowRoutine = StartCoroutine(AnimateThrow(thrownCard2, 1f, 1));

        Debug.Log(
            "[FOLD V29] seat=" + seat +
            " independent throw copies=" + activeThrowCount +
            " duration=" + throwDuration.ToString("F2") + "s"
        );
    }

    private void EnsureDetachedFromHand()
    {
        if (cardManager == null)
            cardManager = FindFirstObjectByType<CardManager>();

        if (cardManager != null)
            cardManager.DetachHoleCardsForFold(seat);
        else
            Debug.LogWarning("[FOLD] seat=" + seat + " no CardManager reference");
    }

    private void TryFindFoldTarget()
    {
        GameObject target = GameObject.Find("FoldAnchor" + (seat + 1));
        if (target == null) target = GameObject.Find("FoldAnchor");
        if (target == null) target = GameObject.Find("PotArchorn");
        if (target == null) target = GameObject.Find("PotAnchor");
        if (target != null) foldTarget = target.transform;
    }

    // Used only as an emergency fallback if the Animator or game is paused.
    public void ForceLandCards()
    {
        if (foldTarget == null) TryFindFoldTarget();
        if (foldTarget == null) return;

        EnsureDetachedFromHand();
        holdingCards = false;
        cardsThrown = true;
        StopThrowCoroutines();

        // In an emergency do NOT snap original CardManager cards onto the
        // table: only independently owned throw visuals are allowed there.
        if (thrownCard1 == null) thrownCard1 = SpawnThrowVisual(card1, 1);
        if (thrownCard2 == null) thrownCard2 = SpawnThrowVisual(card2, 2);

        SnapCardToTable(thrownCard1, -1f);
        SnapCardToTable(thrownCard2, 1f);

        Debug.LogWarning("[FOLD V29] seat=" + seat + " emergency card landing (copies)");
    }

    private void SnapCardToTable(Transform card, float side)
    {
        if (card == null) return;
        card.SetParent(null, true);
        card.position = foldTarget.position
            + foldTarget.forward * landingForwardOffset
            + foldTarget.right * (landingSideSpacing * side)
            + foldTarget.up * landingHeightOffset;
        card.rotation = foldTarget.rotation * Quaternion.Euler(landingEulerOffset);
        MakeCardStatic(card);
    }


    // Alias if your Animation Event is already named DropFoldCards.
    public void DropFoldCards()
    {
        ThrowCards();
    }


    // =========================================================
    // DECOUPLED VISUAL CARDS
    // =========================================================

    private Transform SpawnThrowVisual(Transform original, int index)
    {
        if (original == null)
            return null;

        // Clone BEFORE hiding original renderers. It preserves the actual
        // Python-assigned card texture, world position, rotation and scale.
        GameObject copy = Instantiate(original.gameObject);
        copy.name = "FoldThrowVisual_Seat" + seat + "_Card" + index;
        copy.transform.SetParent(null, true);
        copy.transform.SetPositionAndRotation(original.position, original.rotation);
        copy.transform.localScale = original.lossyScale;

        // Some user prefabs have Animator/other scripts; throw copy must be
        // purely visual. We never let external behaviours drive its transform.
        foreach (Animator a in copy.GetComponentsInChildren<Animator>(true))
            a.enabled = false;
        foreach (MonoBehaviour behaviour in copy.GetComponentsInChildren<MonoBehaviour>(true))
            behaviour.enabled = false;

        MakeCardStatic(copy.transform);

        // Hide original in-hand renderers: they may be repositioned by
        // CardManager, but they cannot be seen until NewHand destroys them.
        foreach (Renderer renderer in original.GetComponentsInChildren<Renderer>(true))
            renderer.enabled = false;

        return copy.transform;
    }

    private void ClearThrownVisuals()
    {
        if (thrownCard1 != null)
            Destroy(thrownCard1.gameObject);
        if (thrownCard2 != null)
            Destroy(thrownCard2.gameObject);
        thrownCard1 = null;
        thrownCard2 = null;
    }

    // =========================================================
    // SCRIPTED THROW
    // =========================================================

    private IEnumerator AnimateThrow(
        Transform card,
        float sideSign,
        int cardIndex
    )
    {
        if (card == null || foldTarget == null)
            yield break;

        // Card must no longer inherit motion/scale from the fly.
        card.SetParent(null, true);

        MakeCardStatic(card);

        Vector3 startPosition = card.position;
        Quaternion startRotation = card.rotation;

        Vector3 sideDirection =
            foldTarget.right * (
                landingSideSpacing *
                sideSign
            );

        Vector3 randomOffset =
            foldTarget.right *
            Random.Range(
                -randomLandingOffset,
                randomLandingOffset
            )
            +
            foldTarget.forward *
            Random.Range(
                -randomLandingOffset,
                randomLandingOffset
            );

        Vector3 endPosition =
            foldTarget.position +
            foldTarget.forward * landingForwardOffset +
            sideDirection +
            randomOffset +
            foldTarget.up * landingHeightOffset;

        float landingYaw =
            Random.Range(
                -randomLandingYaw,
                randomLandingYaw
            );

        Quaternion finalRotation =
            foldTarget.rotation *
            Quaternion.Euler(
                landingEulerOffset +
                new Vector3(
                    0f,
                    landingYaw,
                    0f
                )
            );

        float turns =
            Random.Range(
                minRotationTurns,
                maxRotationTurns
            );

        // Alternate rotation direction between the two cards.
        float rotationDirection =
            sideSign < 0f ? -1f : 1f;

        Quaternion spinRotation =
            Quaternion.Euler(
                Random.Range(-70f, 70f),
                360f * turns * rotationDirection,
                Random.Range(-80f, 80f)
            );

        Quaternion throwRotation =
            startRotation *
            spinRotation;

        float duration =
            Mathf.Max(
                0.05f,
                throwDuration
            );

        float elapsed = 0f;

        while (
            elapsed < duration &&
            card != null
        )
        {
            elapsed += Time.deltaTime;

            float t =
                Mathf.Clamp01(
                    elapsed / duration
                );

            // Smooth horizontal travel.
            float smoothT =
                t * t *
                (3f - 2f * t);

            Vector3 position =
                Vector3.Lerp(
                    startPosition,
                    endPosition,
                    smoothT
                );

            // One short arc. At t=0 and t=1 this is exactly zero.
            position +=
                Vector3.up *
                Mathf.Sin(
                    Mathf.PI * t
                ) *
                throwArcHeight;

            card.position = position;

            // First most of the visible spin happens,
            // then the card settles into the FoldTarget rotation.
            if (t < 0.78f)
            {
                float spinT =
                    Mathf.Clamp01(
                        t / 0.78f
                    );

                card.rotation =
                    Quaternion.Slerp(
                        startRotation,
                        throwRotation,
                        spinT
                    );
            }
            else
            {
                float settleT =
                    Mathf.Clamp01(
                        (t - 0.78f) /
                        0.22f
                    );

                card.rotation =
                    Quaternion.Slerp(
                        throwRotation,
                        finalRotation,
                        settleT
                    );
            }

            yield return null;
        }

        if (card != null)
        {
            // HARD STOP.
            // No Rigidbody, no remaining velocity, no endless flying.
            card.position = endPosition;
            card.rotation = finalRotation;

            MakeCardStatic(card);
        }

        if (cardIndex == 0)
            card1ThrowRoutine = null;
        else
            card2ThrowRoutine = null;

        activeThrowCount = Mathf.Max(0, activeThrowCount - 1);

        if (activeThrowCount == 0 && debugLogs)
            Debug.Log("[FOLD] seat=" + seat + " ALL CARDS LANDED - safe to continue game");

        if (debugLogs)
        {
            Debug.Log(
                "[FOLD] seat=" + seat +
                " card " + (cardIndex + 1) +
                " landed and STOPPED"
            );
        }
    }


    // =========================================================
    // HAND FOLLOW
    // =========================================================

    private void FollowHand(
        Transform card,
        Vector3 localOffset
    )
    {
        if (card == null || handAnchor == null)
            return;

        card.position =
            handAnchor.TransformPoint(
                localOffset
            );

        card.rotation =
            handAnchor.rotation *
            Quaternion.Euler(
                heldEulerOffset
            );
    }


    // =========================================================
    // HELPERS
    // =========================================================

    private void MakeCardStatic(
        Transform card
    )
    {
        if (card == null)
            return;

        Rigidbody rb =
            card.GetComponent<Rigidbody>();

        if (rb == null)
            return;

#if UNITY_6000_0_OR_NEWER
        rb.linearVelocity =
            Vector3.zero;
#else
        rb.velocity =
            Vector3.zero;
#endif

        rb.angularVelocity =
            Vector3.zero;

        rb.useGravity = false;
        rb.isKinematic = true;
    }


    private void StopThrowCoroutines()
    {
        if (card1ThrowRoutine != null)
        {
            StopCoroutine(
                card1ThrowRoutine
            );

            card1ThrowRoutine = null;
        }

        if (card2ThrowRoutine != null)
        {
            StopCoroutine(
                card2ThrowRoutine
            );

            card2ThrowRoutine = null;
        }

        activeThrowCount = 0;
    }
}
