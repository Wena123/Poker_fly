using System;
using System.Collections;
using UnityEngine;

public class FlyAnimationController : MonoBehaviour
{
    [Header("Animator")]
    public Animator animator;

    [Header("Fold Animation")]
    [Tooltip("Animator STATE name for FOLD (the state must exist in the Animator Controller).")]
    public string foldStateName = "Fly_Fold";

    [Tooltip("Crossfade duration in seconds when starting Fly_Fold.")]
    public float foldTransitionSeconds = 0.06f;

    [Header("Safety")]
    [Tooltip("Awaryjny timeout. Jezeli Animation Event nie odpali, Python nie zablokuje sie na zawsze.")]
    public float animationTimeout = 8.0f;

    private bool busy;
    private Action animationFinishedCallback;
    private Coroutine animationWatchdog;
    private int animationSerial;
    private string currentAction = "";
    private bool waitingForFoldLanding = false;
    private Coroutine foldLandingWaitRoutine;

    public bool IsBusy => busy;

    private void Awake()
    {
        if (animator == null)
            animator = GetComponent<Animator>();
    }

    public void PlayAction(string action, Action onFinished = null)
    {
        if (animator == null)
        {
            Debug.LogError(name + ": BRAK ANIMATORA!");
            onFinished?.Invoke();
            return;
        }

        action = (action ?? "").Trim().ToUpperInvariant();

        if (
            action == "ALL-IN" ||
            action == "ALL_IN" ||
            action == "ALLIN" ||
            action == "ALL IN"
        )
            action = "RAISE";

        if (busy)
        {
            // Przy poprawnym handshake Python nie powinien wyslac kolejnej
            // animacji zanim poprzednia sie skonczy. Mimo to nie pozwalamy
            // na deadlock - oddajemy DONE zamiast blokowac Pythona na zawsze.
            Debug.LogWarning(name + ": animacja nadal trwa, pomijam " + action);
            onFinished?.Invoke();
            return;
        }

        animationFinishedCallback = onFinished;
        currentAction = action;
        waitingForFoldLanding = false;

        switch (action)
        {
            case "THINK":
                PlayTrigger("Think", "Fly_Think", "THINK");
                break;

            case "CALL":
                PlayTrigger("Call", "Fly_Call", "CALL");
                break;

            case "RAISE":
                PlayTrigger("Raise", "Fly_Raise", "RAISE");
                break;

            case "FOLD":
                PlayFoldState();
                break;

            case "IDLE":
                FinishWithoutAnimation();
                break;

            default:
                Debug.LogWarning(name + ": nieznana animacja: " + action);
                FinishWithoutAnimation();
                break;
        }
    }

    // FOLD works by crossfading directly to the Animator state.
    // No Fold trigger or Any State -> Fly_Fold transition is required.
    // You DO need a state called Fly_Fold containing the actual Fold clip.
    private void PlayFoldState()
    {
        string requested = string.IsNullOrWhiteSpace(foldStateName)
            ? "Fly_Fold"
            : foldStateName.Trim();

        // Animator.HasState can resolve both short and full state hashes.
        string fullPath = requested.Contains(".")
            ? requested
            : "Base Layer." + requested;

        bool hasFullPath = animator.HasState(0, Animator.StringToHash(fullPath));
        bool hasShortName = animator.HasState(0, Animator.StringToHash(requested));

        if (!hasFullPath && !hasShortName)
        {
            Debug.LogError(
                "[FlyAnimationController] " + name +
                ": BRAK stanu animacji FOLD ('" + requested +
                "') w Animator Controller. Dodaj clip Fly_Fold jako state " +
                "o nazwie Fly_Fold do Base Layer."
            );
            FinishWithoutAnimation();
            return;
        }

        string playbackState = hasFullPath ? fullPath : requested;

        busy = true;
        animationSerial++;
        ResetActionTriggers();

        animator.CrossFadeInFixedTime(
            playbackState,
            Mathf.Max(0f, foldTransitionSeconds),
            0,
            0f
        );

        Debug.Log(name + " -> FOLD [" + playbackState + "]");

        if (animationWatchdog != null)
            StopCoroutine(animationWatchdog);

        animationWatchdog = StartCoroutine(
            WatchAnimation(playbackState, animationSerial)
        );
    }

    private void PlayTrigger(string triggerName, string stateName, string logName)
    {
        busy = true;
        animationSerial++;

        ResetActionTriggers();
        animator.SetTrigger(triggerName);

        Debug.Log(name + " -> " + logName);

        if (animationWatchdog != null)
            StopCoroutine(animationWatchdog);

        animationWatchdog = StartCoroutine(
            WatchAnimation(stateName, animationSerial)
        );
    }

    private IEnumerator WatchAnimation(string stateName, int serial)
    {
        float startedAt = Time.realtimeSinceStartup;
        bool enteredState = false;

        while (busy && serial == animationSerial)
        {
            AnimatorStateInfo state = animator.GetCurrentAnimatorStateInfo(0);

            if (state.IsName(stateName))
            {
                enteredState = true;

                // Backup dla Animation Event. Event powinien zakonczyc animacje,
                // ale jezeli Unity ominie event na ostatniej klatce, ten kod
                // sam wysle DONE po dojsciu prawie do konca klipu.
                if (!animator.IsInTransition(0) && state.normalizedTime >= 0.985f)
                {
                    animationWatchdog = null;
                    FinishCurrentAnimation("watchdog");
                    yield break;
                }
            }

            if (Time.realtimeSinceStartup - startedAt >= animationTimeout)
            {
                Debug.LogWarning(
                    name + ": timeout animacji " + stateName +
                    (enteredState ? " (stan zostal uruchomiony)" : " (Animator nie wszedl w stan!)")
                );

                animationWatchdog = null;
                FinishCurrentAnimation("timeout");
                yield break;
            }

            yield return null;
        }

        animationWatchdog = null;
    }

    // Animation Event at the end of Think / Call / Raise / Fold.
    public void AnimationFinished()
    {
        FinishCurrentAnimation("event");
    }

    private void FinishCurrentAnimation(string source)
    {
        if (!busy || waitingForFoldLanding)
            return;

        animationSerial++;

        if (animationWatchdog != null)
        {
            StopCoroutine(animationWatchdog);
            animationWatchdog = null;
        }

        ResetActionTriggers();

        // The fly can return to Idle while cards are still flying.
        // But Python MUST NOT receive animation_done until the cards land.
        if (currentAction == "FOLD")
        {
            FoldCardController fold = GetComponent<FoldCardController>();
            if (fold != null && fold.HasCards)
            {
                // Fallback if ThrowCards Animation Event wasn't fired.
                if (!fold.HasReleasedCards)
                {
                    Debug.LogWarning(name + ": ThrowCards event missing - starting throw at animation end");
                    fold.ThrowCards();
                }

                animator.CrossFade("Fly_idle", 0.08f);

                if (fold.IsThrowInProgress)
                {
                    waitingForFoldLanding = true;
                    foldLandingWaitRoutine = StartCoroutine(
                        WaitForFoldLanding(fold, animationSerial, source)
                    );
                    return;
                }
            }
        }

        animator.CrossFade("Fly_idle", 0.08f);
        CompleteAction(source);
    }

    private IEnumerator WaitForFoldLanding(FoldCardController fold, int serial, string source)
    {
        float startedAt = Time.realtimeSinceStartup;
        float timeout = Mathf.Max(animationTimeout, fold.throwDuration + 3f);

        Debug.Log(name + " -> FOLD clip finished, waiting for cards to LAND...");

        while (busy && serial == animationSerial && fold != null && fold.IsThrowInProgress)
        {
            if (Time.realtimeSinceStartup - startedAt > timeout)
            {
                Debug.LogWarning(name + ": fold throw exceeded timeout; force landing cards");
                fold.ForceLandCards();
                break;
            }

            yield return null;
        }

        foldLandingWaitRoutine = null;

        if (busy && serial == animationSerial)
        {
            waitingForFoldLanding = false;
            CompleteAction("fold cards landed after " + source);
        }
    }

    private void CompleteAction(string source)
    {
        if (!busy)
            return;

        busy = false;
        currentAction = "";
        waitingForFoldLanding = false;
        animationSerial++;

        Debug.Log(name + " -> ANIMATION FINISHED [" + source + "]");

        Action callback = animationFinishedCallback;
        animationFinishedCallback = null;
        callback?.Invoke();
    }

    private void FinishWithoutAnimation()
    {
        if (foldLandingWaitRoutine != null)
        {
            StopCoroutine(foldLandingWaitRoutine);
            foldLandingWaitRoutine = null;
        }

        busy = false;
        currentAction = "";
        waitingForFoldLanding = false;

        Action callback = animationFinishedCallback;
        animationFinishedCallback = null;
        callback?.Invoke();
    }

    private void ResetActionTriggers()
    {
        animator.ResetTrigger("Think");
        animator.ResetTrigger("Call");
        animator.ResetTrigger("Raise");
    }

    private void OnDisable()
    {
        if (animationWatchdog != null)
        {
            StopCoroutine(animationWatchdog);
            animationWatchdog = null;
        }

        if (foldLandingWaitRoutine != null)
        {
            StopCoroutine(foldLandingWaitRoutine);
            foldLandingWaitRoutine = null;
        }

        busy = false;
        waitingForFoldLanding = false;
        currentAction = "";
        animationFinishedCallback = null;
    }
}
