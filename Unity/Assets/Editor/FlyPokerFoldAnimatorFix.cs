#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

/// <summary>
/// Repairs the Animator Controller used by the four FlyPoker flies:
///  - Ensures Base Layer contains Fly_Fold with a real AnimationClip.
///  - Removes an unconditional Any State -> Fly_idle transition, which can
///    immediately interrupt other states (including Fly_Fold).
///
/// Usage: select the Fly_Fold clip in Project (recommended), then
/// Tools > FlyPoker > Fix FOLD Animator.
/// This is an EDITOR-ONLY tool. It does not change Python or poker logic.
/// </summary>
public static class FlyPokerFoldAnimatorFix
{
    private const string FoldStateName = "Fly_Fold";
    private const string IdleStateName = "Fly_idle";

    [MenuItem("Tools/FlyPoker/Fix FOLD Animator", false, 10)]
    private static void FixFoldAnimator()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog(
                "FlyPoker – FOLD",
                "Zatrzymaj Play Mode przed naprawą kontrolera Animator.",
                "OK"
            );
            return;
        }

        AnimationClip selectedClip = Selection.activeObject as AnimationClip;
        AnimationClip foldClip = IsFoldClip(selectedClip)
            ? selectedClip
            : FindFoldClipInProject();

        if (foldClip == null)
        {
            Debug.LogWarning(
                "[FlyPoker FOLD FIX] Nie znalazłem klipu Fold automatycznie. " +
                "Zaznacz plik Fly_Fold.anim w oknie Project i uruchom " +
                "Tools > FlyPoker > Fix FOLD Animator ponownie. " +
                "Jeżeli klip ma inną nazwę, zmień ją na Fly_Fold."
            );
        }

        int controllersChecked = 0;
        int statesCreated = 0;
        int emptyStatesFilled = 0;
        int removedBadTransitions = 0;
        var processed = new HashSet<int>();
        var messages = new List<string>();

        for (int seat = 0; seat < 4; ++seat)
        {
            string flyName = "Fly" + (seat + 1);
            GameObject fly = GameObject.Find(flyName);
            if (fly == null)
            {
                messages.Add(flyName + ": brak w aktywnej scenie");
                continue;
            }

            Animator animator = fly.GetComponentInChildren<Animator>(true);
            if (animator == null)
            {
                messages.Add(flyName + ": brak komponentu Animator");
                continue;
            }

            AnimatorController controller = GetBaseController(animator.runtimeAnimatorController);
            if (controller == null)
            {
                messages.Add(
                    flyName + ": Animator nie ma zwykłego AnimatorController (" +
                    (animator.runtimeAnimatorController != null
                        ? animator.runtimeAnimatorController.name : "null") + ")"
                );
                continue;
            }

            messages.Add(
                flyName + " -> " + controller.name + " / " +
                animator.gameObject.name
            );

            // Multiple flies typically share one controller asset. Modify it once.
            if (!processed.Add(controller.GetInstanceID()))
                continue;

            controllersChecked++;
            if (controller.layers.Length == 0)
            {
                messages.Add(controller.name + ": Controller nie ma Base Layer");
                continue;
            }

            AnimatorStateMachine machine = controller.layers[0].stateMachine;
            if (machine == null)
            {
                messages.Add(controller.name + ": brak StateMachine");
                continue;
            }

            AnimatorState foldState = null;
            foreach (ChildAnimatorState child in machine.states)
            {
                if (child.state != null && child.state.name == FoldStateName)
                {
                    foldState = child.state;
                    break;
                }
            }

            if (foldState == null)
            {
                if (foldClip == null)
                {
                    messages.Add(
                        controller.name + ": nie utworzono Fly_Fold – brak klipu"
                    );
                }
                else
                {
                    Undo.RegisterCompleteObjectUndo(machine, "FlyPoker: add Fly_Fold state");
                    foldState = machine.AddState(FoldStateName, new Vector3(600, 500, 0));
                    foldState.motion = foldClip;
                    EditorUtility.SetDirty(foldState);
                    statesCreated++;
                    messages.Add(
                        controller.name + ": dodano Fly_Fold -> " + foldClip.name
                    );
                }
            }
            else if (foldState.motion == null)
            {
                if (foldClip != null)
                {
                    Undo.RecordObject(foldState, "FlyPoker: assign Fold clip");
                    foldState.motion = foldClip;
                    EditorUtility.SetDirty(foldState);
                    emptyStatesFilled++;
                    messages.Add(
                        controller.name + ": ustawiono Motion = " + foldClip.name
                    );
                }
                else
                {
                    messages.Add(
                        controller.name + ": Fly_Fold ma pusty Motion – " +
                        "przypisz prawdziwy klip Fold"
                    );
                }
            }
            else
            {
                messages.Add(
                    controller.name + ": Fly_Fold istnieje, Motion = " +
                    foldState.motion.name
                );
            }

            // Some older versions had Any State -> Fly_idle without any
            // conditions or exit time, which overrides played states.
            foreach (AnimatorStateTransition transition in machine.anyStateTransitions)
            {
                if (transition == null || transition.destinationState == null)
                    continue;

                if (
                    transition.destinationState.name == IdleStateName &&
                    transition.conditions.Length == 0 &&
                    !transition.hasExitTime
                )
                {
                    Undo.RegisterCompleteObjectUndo(
                        machine,
                        "FlyPoker: remove unconditional AnyState Idle"
                    );
                    machine.RemoveAnyStateTransition(transition);
                    removedBadTransitions++;
                    messages.Add(
                        controller.name + ": usunięto Any State -> Fly_idle " +
                        "bez warunku"
                    );
                }
            }

            EditorUtility.SetDirty(machine);
            EditorUtility.SetDirty(controller);
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        string result =
            "Kontrolery: " + controllersChecked +
            ", nowe stany FOLD: " + statesCreated +
            ", uzupełnione Motion: " + emptyStatesFilled +
            ", usunięte złe przejścia: " + removedBadTransitions +
            "\n\n" + string.Join("\n", messages);

        Debug.Log("[FlyPoker FOLD FIX]\n" + result);
        EditorUtility.DisplayDialog("FlyPoker – wynik naprawy", result, "OK");
    }

    private static bool IsFoldClip(AnimationClip clip)
    {
        return clip != null &&
               clip.name.IndexOf("fold", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    private static AnimationClip FindFoldClipInProject()
    {
        AnimationClip best = null;
        int bestScore = -1;

        foreach (string guid in AssetDatabase.FindAssets("t:AnimationClip"))
        {
            string assetPath = AssetDatabase.GUIDToAssetPath(guid);
            foreach (UnityEngine.Object item in AssetDatabase.LoadAllAssetsAtPath(assetPath))
            {
                AnimationClip clip = item as AnimationClip;
                if (!IsFoldClip(clip))
                    continue;

                // Prefer the exact filename and a standalone .anim over FBX subclips.
                int score = 0;
                if (clip.name.Equals("Fly_Fold", StringComparison.OrdinalIgnoreCase)) score += 100;
                if (assetPath.EndsWith(".anim", StringComparison.OrdinalIgnoreCase)) score += 20;
                if (clip.name.Equals("Fold", StringComparison.OrdinalIgnoreCase)) score += 10;

                if (score > bestScore)
                {
                    best = clip;
                    bestScore = score;
                }
            }
        }

        return best;
    }

    private static AnimatorController GetBaseController(RuntimeAnimatorController runtime)
    {
        // AnimatorOverrideController is often used on imported prefabs.
        for (int depth = 0; depth < 8; depth++)
        {
            if (runtime is AnimatorController)
                return (AnimatorController)runtime;

            AnimatorOverrideController overridden = runtime as AnimatorOverrideController;
            if (overridden == null)
                break;

            runtime = overridden.runtimeAnimatorController;
        }

        return null;
    }

    [MenuItem("Tools/FlyPoker/Test FOLD (Fly1)", false, 11)]
    private static void TestFoldFly1()
    {
        if (!EditorApplication.isPlaying)
        {
            EditorUtility.DisplayDialog(
                "FlyPoker – FOLD test",
                "Uruchom Play Mode. Możesz testować bez Pythona.",
                "OK"
            );
            return;
        }

        GameObject fly = GameObject.Find("Fly1");
        if (fly == null)
        {
            Debug.LogError("[FlyPoker FOLD TEST] Nie znaleziono Fly1 w scenie.");
            return;
        }

        Animator anim = fly.GetComponentInChildren<Animator>(true);
        if (anim == null)
        {
            Debug.LogError("[FlyPoker FOLD TEST] Brak Animator na Fly1.");
            return;
        }

        FlyAnimationController controller = anim.GetComponent<FlyAnimationController>();
        if (controller == null)
            controller = anim.gameObject.AddComponent<FlyAnimationController>();

        controller.animator = anim;
        Debug.Log(
            "[FlyPoker FOLD TEST] Uruchamiam FOLD na: " + anim.name +
            "; AnimatorController=" +
            (anim.runtimeAnimatorController != null
                ? anim.runtimeAnimatorController.name : "NULL")
        );

        controller.PlayAction("FOLD", () =>
        {
            Debug.Log("[FlyPoker FOLD TEST] Animation done na Fly1.");
        });
    }
}
#endif
