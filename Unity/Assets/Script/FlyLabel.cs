using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Billboard name, stack and action label, with two real card PNG previews.
/// Uses Texture2D from Assets/Resources/cards (no Sprite import required).
/// Python still sends just the two card codes via PokerReceiver.
/// </summary>
public class FlyLabel : MonoBehaviour
{
    [Header("Text")]
    [Tooltip("Existing TextMeshPro 3D label above the fly.")]
    public TMP_Text labelText;

    [Header("Player")]
    [Range(0, 3)] public int seat = 0;
    public string customName = "";

    [Header("Camera")]
    public Camera targetCamera;
    [Tooltip("Extra 180-degree correction, only if the label still faces away from the camera.")]
    public bool flip180 = false;

    [Header("Automatic position above the fly")]
    [Tooltip("Enabled: the whole label follows this fly in world space. The cards automatically follow the NAME.")]
    public bool autoPositionAboveFly = true;

    [Tooltip("Optional. Leave empty: FlyLabel finds Fly1/Fly2/Fly3/Fly4 using Seat or parent hierarchy.")]
    public Transform flyTarget;

    [Tooltip("Vertical gap (world units) between the highest point of the fly model and the bottom of the label.")]
    [Min(0f)] public float spaceAboveFly = 0.06f;

    [Tooltip("Fine adjustment of the whole label in WORLD units. (0,0,0) = auto centered above fly.")]
    public Vector3 labelPositionOffset = Vector3.zero;

    [Tooltip("Used only when the fly has no visible 3D renderers.")]
    [Min(0f)] public float fallbackModelHeight = 0.3f;

    [Header("Display")]
    public bool showStack = true;
    public bool showAction = true;
    public string thinkingText = "THINKING...";

    [Header("Card pictures over the fly")]
    public bool showCardPictures = true;

    [Tooltip("ON: automatically center the two cards above the rendered name, ignoring old Card Pictures Offset values from Inspector. Recommended after manually moving/scaling FlyText.")]
    public bool alwaysCenterCardsAboveName = true;
    [Tooltip("Fine adjustment relative to the NAME center (X=left/right, Y=up/down, Z=depth). 0,0,0 means centered.")]
    public Vector3 cardPicturesOffset = new Vector3(0f, 0.22f, 0f);

    [Tooltip("Gap between the TOP of the fly NAME and the BOTTOM of the cards (world units).")]
    [Min(0f)] public float cardPicturesNameGap = 0.025f;

    // V31 used cardPicturesOffset.y = 0.22 as its default position relative
    // to the object's pivot. V33 anchors directly to the NAME glyph bounds;
    // migrate existing Inspector values so 0 now means perfectly centered.
    [SerializeField, HideInInspector]
    private int cardPicturesLayoutVersion = 0;
    [Tooltip("Size of the two PNG cards in world space. Default card is approx. 0.08 x 0.12 world units.")]
    [Range(0.0005f, 0.008f)]
    public float cardPicturesCanvasScale = 0.0015f;
    [Tooltip("Spacing of the two cards in Canvas units.")]
    public float cardPicturesSpacing = 61f;

    private int currentStack = 1000;
    private string currentAction = "";
    private int currentActionAmount = 0;
    private bool isThinking;
    private bool isEliminated;
    // A player can have zero chips during a hand because they are ALL-IN.
    // Elimination is confirmed only when the hand ends.
    private bool isAllIn;
    private bool hasHoleCards;
    private bool foldedThisHand;
    private string[] currentHoleCards = new string[0];

    // The model's upper-center is calculated once in local fly space,
    // so wing flapping/other animation does not make the label wobble.
    private Transform cachedFlyTarget;
    private Vector3 localFlyTopCenter;
    private bool hasCachedFlyPoint;
    private bool flyWasAutoResolved;

    // V35: preserve the pre-existing TextMeshPro orientation relative to
    // the FlyLabel component. V34 changed the TMP world rotation directly,
    // throwing away the child's 180-degree orientation correction.
    private Transform cachedTextVisual;
    private Quaternion originalTextRelativeRotation = Quaternion.identity;

    private GameObject cardPicturesRoot;
    private RectTransform cardPicturesRect;
    private readonly RawImage[] cardImages = new RawImage[2];
    private readonly string[] shownCardCodes = { "", "" };

    private void OnValidate()
    {
        MigrateCardPicturesLayout();
        // If the user edits the fly or anchor options, recalculate next frame.
        hasCachedFlyPoint = false;
    }

    private void MigrateCardPicturesLayout()
    {
        if (cardPicturesLayoutVersion >= 2)
            return;

        // V30 default Y=-0.19. V31 moved it to +0.22. A saved V31
        // adjustment is preserved as an adjustment relative to +0.22.
        if (cardPicturesLayoutVersion < 1)
            cardPicturesOffset.y = Mathf.Max(0.22f, cardPicturesOffset.y);

        cardPicturesOffset.y -= 0.22f;
        cardPicturesLayoutVersion = 2;
    }

    [ContextMenu("FlyPoker/Reset card alignment to name (automatic)")]
    public void CenterCardPicturesAboveName()
    {
        alwaysCenterCardsAboveName = true;
        cardPicturesOffset = Vector3.zero;
        cardPicturesLayoutVersion = 2;
        cardPicturesNameGap = 0.025f;
        ResolveText();
        if (labelText != null)
            labelText.ForceMeshUpdate();
        UpdatePicturePosition();
    }

    // Kept for older workflows / menu descriptions.
    [ContextMenu("FlyPoker/Center pictures precisely above NAME")]
    private void CenterCardPicturesAboveNameLegacy()
    {
        CenterCardPicturesAboveName();
    }

    private void Awake()
    {
        MigrateCardPicturesLayout();
        ResolveText();
        CacheOriginalTextRotation();
        if (targetCamera == null) targetCamera = Camera.main;
        ResolveFlyTarget();
        RefreshText();
    }

    private void OnEnable()
    {
        MigrateCardPicturesLayout();
        ResolveText();
        CacheOriginalTextRotation();
        ResolveFlyTarget();
        RefreshText();
        RefreshPictures();
    }

    private void LateUpdate()
    {
        // V34: move ALL label contents together, then place the two cards
        // precisely above the NAME's actual rendered glyphs (V33 feature).
        FaceCamera();
        if (autoPositionAboveFly)
        {
            PositionWholeLabelAboveFly();
            // Reorient from the final position, for a moving camera.
            FaceCamera();
            PositionWholeLabelAboveFly();
        }
        UpdatePicturePosition();
    }

    private void OnDisable()
    {
        if (cardPicturesRoot != null)
            cardPicturesRoot.SetActive(false);
    }

    private void OnDestroy()
    {
        if (cardPicturesRoot != null)
            Destroy(cardPicturesRoot);
    }

    private void ResolveText()
    {
        if (labelText == null) labelText = GetComponent<TMP_Text>();
        if (labelText == null) labelText = GetComponentInChildren<TMP_Text>(true);
    }

    // Capture the child TMP's original relative rotation ONCE, before
    // LateUpdate applies billboarding. For a label with its own TMP on the
    // same GameObject there is no additional local rotation to preserve.
    private void CacheOriginalTextRotation()
    {
        if (labelText == null) return;

        Transform visual = labelText.transform;
        if (visual == cachedTextVisual) return;

        cachedTextVisual = visual;
        originalTextRelativeRotation = visual == transform
            ? Quaternion.identity
            : Quaternion.Inverse(transform.rotation) * visual.rotation;
    }

    // =========================================================
    // AUTO FOLLOW: FLY MODEL -> TEXT -> CARD PICTURES
    // =========================================================

    private void ResolveFlyTarget()
    {
        if (flyTarget != null) return;

        string expectedName = "Fly" + (seat + 1);

        // Prefer the fly containing the label (even for nested NameTextAnchor).
        Transform node = transform;
        while (node != null)
        {
            if (node.name == expectedName)
            {
                flyTarget = node;
                flyWasAutoResolved = true;
                hasCachedFlyPoint = false;
                return;
            }
            node = node.parent;
        }

        // Handles a label placed elsewhere in the scene.
        GameObject fly = GameObject.Find(expectedName);
        if (fly != null)
        {
            flyTarget = fly.transform;
            flyWasAutoResolved = true;
            hasCachedFlyPoint = false;
        }
    }

    private void PositionWholeLabelAboveFly()
    {
        if (flyTarget == null) ResolveFlyTarget();
        if (flyTarget == null || labelText == null) return;

        if (!hasCachedFlyPoint || cachedFlyTarget != flyTarget)
            CacheFlyModelTop();

        Vector3 desiredBottomCenter = flyTarget.TransformPoint(localFlyTopCenter)
            + Vector3.up * spaceAboveFly
            + labelPositionOffset;

        // Don't trust the pivot of FlyText: a TMP object can be left aligned,
        // centered, or contain a different number of lines every action.
        // Instead use the center of the ACTUAL rendered text's bottom edge.
        Bounds textBounds = labelText.textBounds;
        Vector3 textBottomCenterLocal = new Vector3(
            textBounds.center.x,
            textBounds.min.y,
            textBounds.center.z
        );
        Vector3 actualBottomCenter =
            labelText.transform.TransformPoint(textBottomCenterLocal);

        // Move ONLY the text, never the fly model (even if FlyLabel was
        // accidentally added to Fly1 instead of FlyText). The card canvas
        // tracks this same TMP object in UpdatePicturePosition().
        labelText.transform.position += desiredBottomCenter - actualBottomCenter;
    }

    private void CacheFlyModelTop()
    {
        cachedFlyTarget = flyTarget;
        hasCachedFlyPoint = true;

        Bounds bounds;
        if (TryFindModelBounds(out bounds))
        {
            Vector3 worldTop = new Vector3(
                bounds.center.x, bounds.max.y, bounds.center.z);
            localFlyTopCenter = flyTarget.InverseTransformPoint(worldTop);
        }
        else
        {
            // A predictable fallback for models without active Renderers.
            localFlyTopCenter = flyTarget.InverseTransformPoint(
                flyTarget.position + Vector3.up * fallbackModelHeight);
        }
    }

    private bool TryFindModelBounds(out Bounds bounds)
    {
        bounds = new Bounds();
        if (flyTarget == null) return false;

        // First look at SkinnedMeshRenderers: usually these are the fruit fly
        // body parts. Ignore the HUD, cards and poker chips.
        SkinnedMeshRenderer[] skins =
            flyTarget.GetComponentsInChildren<SkinnedMeshRenderer>(true);
        bool found = false;

        foreach (SkinnedMeshRenderer renderer in skins)
        {
            if (!IsFlyModelRenderer(renderer)) continue;
            if (!found) { bounds = renderer.bounds; found = true; }
            else bounds.Encapsulate(renderer.bounds);
        }
        if (found) return true;

        // Some fly prefabs use ordinary MeshRenderers instead.
        MeshRenderer[] meshes =
            flyTarget.GetComponentsInChildren<MeshRenderer>(true);
        foreach (MeshRenderer renderer in meshes)
        {
            if (!IsFlyModelRenderer(renderer)) continue;
            if (!found) { bounds = renderer.bounds; found = true; }
            else bounds.Encapsulate(renderer.bounds);
        }
        return found;
    }

    private bool IsFlyModelRenderer(Renderer renderer)
    {
        if (renderer == null || !renderer.enabled ||
            !renderer.gameObject.activeInHierarchy) return false;

        // Never measure our own name label or its card canvas.
        if (labelText != null &&
            (renderer.transform == labelText.transform ||
             renderer.transform.IsChildOf(labelText.transform))) return false;
        if (renderer.GetComponent<TMP_Text>() != null) return false;
        if (renderer.GetComponentInParent<Canvas>() != null) return false;

        string n = renderer.gameObject.name.ToLowerInvariant();
        if (n.Contains("card") || n.Contains("chip") ||
            n.Contains("anchor") || n.Contains("text") ||
            n.Contains("label") || n.Contains("pot") ||
            n.Contains("bet")) return false;
        return true;
    }

    [ContextMenu("FlyPoker/Recalculate position above fly")]
    private void RecalculatePositionAboveFly()
    {
        hasCachedFlyPoint = false;
        ResolveText();
        ResolveFlyTarget();
        if (Application.isPlaying)
        {
            FaceCamera();
            PositionWholeLabelAboveFly();
            UpdatePicturePosition();
        }
    }

    private void FaceCamera()
    {
        if (targetCamera == null) targetCamera = Camera.main;
        if (targetCamera == null) return;
        ResolveText();
        if (labelText == null) return;
        CacheOriginalTextRotation();

        // Rotate ONLY the TMP visual, never the fly model.
        // Keep its original 180-degree local correction. V34 lost that
        // correction, so some labels appeared backward/mirrored.
        Transform visual = labelText.transform;
        Vector3 direction = targetCamera.transform.position - visual.position;
        if (direction.sqrMagnitude < 0.0001f) return;

        Quaternion billboardRotation = Quaternion.LookRotation(direction, Vector3.up);
        visual.rotation = billboardRotation * originalTextRelativeRotation;
        if (flip180)
            visual.Rotate(0f, 180f, 0f, Space.Self);
    }

    public void SetSeat(int newSeat)
    {
        int clamped = Mathf.Clamp(newSeat, 0, 3);
        if (seat != clamped && flyWasAutoResolved)
        {
            flyTarget = null;
            flyWasAutoResolved = false;
        }
        seat = clamped;
        hasCachedFlyPoint = false;
        ResolveFlyTarget();
        if (cardPicturesRoot != null)
            cardPicturesRoot.name = "Fly" + (seat + 1) + "_CardPictures_Auto";
        RefreshText();
    }

    public void SetStack(int amount)
    {
        currentStack = Mathf.Max(0, amount);

        if (currentStack > 0)
        {
            // The player still has chips (or won the all-in pot).
            isAllIn = false;
            isEliminated = false;
        }
        else if (!isEliminated)
        {
            // Zero DURING the hand means waiting for showdown, not a bust.
            // Do not hide the player's cards here.
            isAllIn = true;
        }

        RefreshText();
    }

    public void SetThinking(bool thinking)
    {
        isThinking = thinking;
        if (thinking)
        {
            currentAction = "";
            currentActionAmount = 0;
        }
        RefreshText();
    }

    public void SetAction(string action) { SetAction(action, 0); }

    public void SetAction(string action, int amount)
    {
        isThinking = false;
        currentAction = string.IsNullOrWhiteSpace(action)
            ? "" : action.Trim().ToUpperInvariant();
        currentActionAmount = Mathf.Max(0, amount);

        // The action arrives before the next authoritative stack update.
        // Show ALL-IN immediately, even before SetStack(0) arrives.
        if (currentAction == "ALL-IN" || currentAction == "ALL_IN" ||
            currentAction == "ALLIN")
        {
            isAllIn = true;
            isEliminated = false;
        }

        if (currentAction == "FOLD")
        {
            foldedThisHand = true;
            RefreshPictures();
        }
        RefreshText();
    }

    public void ClearAction()
    {
        isThinking = false;
        currentAction = "";
        currentActionAmount = 0;
        RefreshText();
    }

    public void ResetForNewHand()
    {
        isThinking = false;
        currentAction = "";
        currentActionAmount = 0;
        // Only between hands is a zero stack sufficient to mark an eliminated seat.
        isAllIn = false;
        isEliminated = currentStack <= 0;
        foldedThisHand = false;
        hasHoleCards = false;
        currentHoleCards = new string[0];
        RefreshText();
        RefreshPictures();
    }

    /// <summary>
    /// Called by PokerReceiver after the Python hand_end message, when the
    /// final post-payout stacks have already been delivered.
    /// </summary>
    public void ConfirmHandEnded()
    {
        isThinking = false;
        isAllIn = false;

        if (currentStack <= 0)
        {
            SetEliminated(true);
        }
        else
        {
            isEliminated = false;
            RefreshText();
            RefreshPictures();
        }
    }

    public void SetEliminated(bool eliminated)
    {
        isEliminated = eliminated;
        isAllIn = false;
        isThinking = false;
        if (eliminated)
        {
            currentAction = "";
            currentActionAmount = 0;
            hasHoleCards = false;
        }
        RefreshText();
        RefreshPictures();
    }

    /// <summary>Show actual PNGs from Resources/cards/AH, etc. No codes are printed.</summary>
    public void SetHoleCards(string[] cards)
    {
        if (cards == null || cards.Length < 2 ||
            string.IsNullOrWhiteSpace(cards[0]) || string.IsNullOrWhiteSpace(cards[1]))
        {
            hasHoleCards = false;
            currentHoleCards = new string[0];
        }
        else
        {
            hasHoleCards = true;
            currentHoleCards = new[] { cards[0], cards[1] };
        }
        RefreshPictures();
    }

    public void ForceRefresh()
    {
        ResolveText();
        RefreshText();
        RefreshPictures();
    }

    private void RefreshText()
    {
        ResolveText();
        if (labelText == null) return;

        string playerName = string.IsNullOrWhiteSpace(customName)
            ? "FLY " + (seat + 1) : customName.Trim();
        if (isEliminated)
        {
            labelText.text = playerName + "\nELIMINATED";
            labelText.ForceMeshUpdate();
            return;
        }

        string text = playerName;
        if (showStack) text += "\n" + currentStack + " CHIPS";
        if (showAction)
        {
            if (isAllIn)
            {
                // An ALL-IN player's turn is over, but the player remains
                // eligible to win the pot until the hand ends.
                bool explicitAllIn = currentAction == "ALL-IN" ||
                    currentAction == "ALL_IN" || currentAction == "ALLIN";
                text += "\nALL-IN" +
                    (explicitAllIn && currentActionAmount > 0
                        ? " " + currentActionAmount
                        : "");
            }
            else if (isThinking) text += "\n" + thinkingText;
            else if (!string.IsNullOrEmpty(currentAction))
                text += "\n" + FormatAction(currentAction, currentActionAmount);
        }
        labelText.text = text;
        labelText.ForceMeshUpdate();
    }

    private string FormatAction(string action, int amount)
    {
        bool usesAmount = amount > 0 &&
            (action == "CALL" || action == "BET" || action == "RAISE" ||
             action == "ALL-IN" || action == "ALL_IN" || action == "ALLIN");
        return action.Replace("_", "-") + (usesAmount ? " " + amount : "");
    }

    private void BuildPictureCanvas()
    {
        if (cardPicturesRoot != null) return;

        cardPicturesRoot = new GameObject(
            "Fly" + (seat + 1) + "_CardPictures_Auto",
            typeof(RectTransform), typeof(Canvas));
        cardPicturesRect = cardPicturesRoot.GetComponent<RectTransform>();
        cardPicturesRect.sizeDelta = new Vector2(160, 115);

        Canvas canvas = cardPicturesRoot.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;
        canvas.overrideSorting = true;
        canvas.sortingOrder = 150;

        for (int i = 0; i < 2; i++)
        {
            GameObject imageObject = new GameObject(
                "HoleCard" + (i + 1), typeof(RectTransform), typeof(RawImage));
            imageObject.transform.SetParent(cardPicturesRoot.transform, false);
            RectTransform rect = imageObject.GetComponent<RectTransform>();
            rect.anchorMin = new Vector2(0.5f, 0.5f);
            rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.sizeDelta = new Vector2(58f, 84f); // PNGs are 500 x 726
            rect.anchoredPosition = new Vector2((i == 0 ? -0.5f : 0.5f) * cardPicturesSpacing, 0f);
            cardImages[i] = imageObject.GetComponent<RawImage>();
            cardImages[i].raycastTarget = false;
            cardImages[i].gameObject.SetActive(false);
        }
    }

    private void RefreshPictures()
    {
        bool visible = showCardPictures && hasHoleCards && !foldedThisHand && !isEliminated;
        if (!visible)
        {
            if (cardPicturesRoot != null) cardPicturesRoot.SetActive(false);
            return;
        }

        BuildPictureCanvas();
        cardPicturesRoot.SetActive(true);
        for (int i = 0; i < 2; i++)
        {
            string code = currentHoleCards[i].Trim().ToUpperInvariant();
            if (shownCardCodes[i] != code)
            {
                shownCardCodes[i] = code;
                cardImages[i].texture = Resources.Load<Texture2D>("cards/" + code);
                if (cardImages[i].texture == null)
                    Debug.LogWarning("[FlyLabel] Missing PNG: Assets/Resources/cards/" + code + ".png");
            }
            cardImages[i].gameObject.SetActive(cardImages[i].texture != null);
        }
        UpdatePicturePosition();
    }

    /// <summary>
    /// Get the top-center of the first rendered line in CAMERA SPACE.
    /// Works even if Fly1's TMP object was previously moved, rescaled,
    /// rotated or assigned a different pivot/alignment. Camera space also
    /// fixes separation caused by inverted local TMP up vectors.
    /// </summary>
    private bool TryGetNameTopCenter(out Vector3 worldTopCenter)
    {
        Transform visual = labelText != null ? labelText.transform : transform;
        worldTopCenter = visual.position;
        if (labelText == null) return false;

        // Ensures the bounds match the most recent text/transform adjustments.
        labelText.ForceMeshUpdate();
        TMP_TextInfo info = labelText.textInfo;
        if (info == null || info.lineCount < 1 || info.characterCount < 1)
            return false;

        Vector3 right = targetCamera != null
            ? targetCamera.transform.right : visual.right;
        Vector3 up = targetCamera != null
            ? targetCamera.transform.up : visual.up;
        Vector3 forward = Vector3.Cross(right, up).normalized;
        Vector3 origin = visual.position;

        TMP_LineInfo firstLine = info.lineInfo[0];
        int first = Mathf.Max(0, firstLine.firstCharacterIndex);
        int last = Mathf.Min(info.characterCount - 1, firstLine.lastCharacterIndex);

        float minX = float.PositiveInfinity;
        float maxX = float.NegativeInfinity;
        float maxY = float.NegativeInfinity;
        float sumDepth = 0f;
        int visibleCorners = 0;

        for (int i = first; i <= last; i++)
        {
            TMP_CharacterInfo character = info.characterInfo[i];
            if (!character.isVisible) continue;

            Vector3[] corners =
            {
                character.bottomLeft,
                character.bottomRight,
                character.topLeft,
                character.topRight
            };
            for (int j = 0; j < corners.Length; j++)
            {
                Vector3 delta = visual.TransformPoint(corners[j]) - origin;
                float x = Vector3.Dot(delta, right);
                float y = Vector3.Dot(delta, up);
                minX = Mathf.Min(minX, x);
                maxX = Mathf.Max(maxX, x);
                maxY = Mathf.Max(maxY, y);
                sumDepth += Vector3.Dot(delta, forward);
                visibleCorners++;
            }
        }

        if (visibleCorners == 0)
            return false;

        worldTopCenter = origin
            + right * ((minX + maxX) * 0.5f)
            + up * maxY
            + forward * (sumDepth / visibleCorners);
        return true;
    }

    private void UpdatePicturePosition()
    {
        if (cardPicturesRoot == null || !cardPicturesRoot.activeSelf)
            return;

        if (targetCamera == null) targetCamera = Camera.main;
        if (labelText == null) ResolveText();

        float canvasScale = Mathf.Max(0.0001f, cardPicturesCanvasScale);
        cardPicturesRect.localScale = Vector3.one * canvasScale;

        // Place the images in camera/view space (the direction the player
        // perceives as UP), rather than using a potentially rotated TMP axis.
        // This is robust when Fly1 has a previously edited text transform.
        float cardHalfHeight = 84f * canvasScale * 0.5f;
        Vector3 viewUp = targetCamera != null
            ? targetCamera.transform.up : labelText.transform.up;
        Vector3 viewRight = targetCamera != null
            ? targetCamera.transform.right : labelText.transform.right;
        Vector3 viewForward = targetCamera != null
            ? targetCamera.transform.forward : labelText.transform.forward;

        Vector3 nameTopCenter;
        if (!TryGetNameTopCenter(out nameTopCenter))
            nameTopCenter = labelText != null
                ? labelText.transform.position : transform.position;

        // Automatic mode deliberately ignores old per-fly Inspector offsets.
        // Custom offsets remain available when this checkbox is unchecked.
        Vector3 fineOffset = alwaysCenterCardsAboveName
            ? Vector3.zero : cardPicturesOffset;

        cardPicturesRect.position = nameTopCenter
            + viewUp * (cardHalfHeight + cardPicturesNameGap + fineOffset.y)
            + viewRight * fineOffset.x
            + viewForward * fineOffset.z;

        // Preserve the proven V31 front-facing orientation (no mirrored PNGs).
        if (targetCamera != null)
        {
            Vector3 toCamera = targetCamera.transform.position - cardPicturesRect.position;
            if (toCamera.sqrMagnitude > 0.0001f)
                cardPicturesRect.rotation = Quaternion.LookRotation(-toCamera, Vector3.up);
        }

        // Symmetric offsets: the two cards always share the NAME's center.
        for (int i = 0; i < 2; i++)
        {
            if (cardImages[i] == null) continue;
            cardImages[i].rectTransform.anchoredPosition = new Vector2(
                (i == 0 ? -0.5f : 0.5f) * cardPicturesSpacing, 0f);
        }
    }
}
