#include "clang/AST/AST.h"
#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendPluginRegistry.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <iomanip>
#include <ios>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <tuple>

using namespace std;
using namespace clang;

// #define DEBUG_PLUGIN
#ifndef DEBUG_PLUGIN
#define DBG(...)
#define DBG_NOTE(...)
#else
#define DBG(expr)                                                      \
    do                                                                 \
    {                                                                  \
        cerr << "\033[33m" #expr ": "                                  \
             << boolalpha << (expr) << boolalpha << "\033[0m" << endl; \
    } while (false)
// ]]

#define DBG_NOTE(expr)                              \
    do                                              \
    {                                               \
        cerr << "\033[32m" #expr "\033[0m" << endl; \
    } while (false)
// ]]
#endif // DEBUG_PLUGIN

namespace
{
//                      val, delim
using CharInfo = tuple<char, char>;
//                          value,          type                context         last
using StructInfo = tuple<const APValue &, const QualType &, const ASTContext &, bool>;
//                          value,          type                context
using ValueInfo = tuple<const APValue &, const QualType &, const ASTContext &>;
//                              record,         last
using RecordInfo = tuple<const CXXRecordDecl *, bool>;

inline constexpr decltype(auto) OUTPUT_EQ = ":=";

inline constexpr auto char_delim = '\'';
inline constexpr auto string_delim = '"';
inline constexpr auto escape_char = '\\';

static inline bool HasAnyFields(const CXXRecordDecl *decl);

static inline bool BaseHasAnyFields(const CXXBaseSpecifier &base)
{
    return HasAnyFields(base.getType()->getAsCXXRecordDecl());
}

static inline bool HasAnyFields(const CXXRecordDecl *decl)
{
    if (decl == nullptr)
    {
        return false;
    }

    if (!decl->field_empty())
    {
        return true;
    }
    return any_of(decl->bases_begin(), decl->bases_end(), BaseHasAnyFields);
}

/**
 * @brief Get the first parent node of type `Parent` for `node` in the AST that matches
 *        the given predicate.
 *
 * @tparam Parent   The type of the parent node.
 * @param context   The AST context.
 * @param node      The starting node.
 * @param pred      A boolean predicate than accepts a `const Parent&`.
 *
 * @return const Parent*    Returns the first matching parent or `nullptr` if no such parent exists.
 */
template <typename Parent, typename Predicate, typename = enable_if_t<is_invocable_r_v<bool, Predicate, const Parent &>>>
const Parent *GetParent(ASTContext &context, const ast_type_traits::DynTypedNode &node, const Predicate &pred)
{
    auto &&parents = context.getParents(node);
    for (auto &&dynamic_parent : parents)
    {
        if (const Parent *parent = dynamic_parent.get<Parent>();
            parent != nullptr && pred(*parent))
        {
            return parent;
        }
        if (const Parent *matching_ancestor = GetParent<Parent>(context, dynamic_parent, pred);
            matching_ancestor != nullptr)
        {
            return matching_ancestor;
        }
    }
    return nullptr;
}

template <typename Parent>
const Parent *GetParent(ASTContext &context, const ast_type_traits::DynTypedNode &node)
{
    return GetParent<Parent>(context, node, [](const Parent &) { return true; });
}

template <typename Parent, typename Node, typename Predicate, typename = enable_if_t<is_invocable_r_v<bool, Predicate, const Parent &>>>
const Parent *GetParent(ASTContext &context, const Node &node, const Predicate &pred)
{
    return GetParent<Parent>(context, ast_type_traits::DynTypedNode::create(node), pred);
}

template <typename Parent, typename Node>
const Parent *GetParent(ASTContext &context, const Node &node)
{
    return GetParent<Parent>(context, ast_type_traits::DynTypedNode::create(node));
}

template <typename Parent, typename Predicate, typename = enable_if_t<is_invocable_r_v<bool, Predicate, const Parent &>>>
bool HasParent(ASTContext &context, const ast_type_traits::DynTypedNode &node, const Predicate &pred)
{
    return GetParent<Parent>(context, node, pred) != nullptr;
}

template <typename Parent>
bool HasParent(ASTContext &context, const ast_type_traits::DynTypedNode &node)
{
    return GetParent<Parent>(context, node) != nullptr;
}

template <typename Parent, typename Node, typename Predicate, typename = enable_if_t<is_invocable_r_v<bool, Predicate, const Parent &>>>
bool HasParent(ASTContext &context, const Node &node, const Predicate &pred)
{
    return GetParent<Parent>(context, node, pred) != nullptr;
}

template <typename Parent, typename Node>
bool HasParent(ASTContext &context, const Node &node)
{
    return GetParent<Parent>(context, node) != nullptr;
}

/**
 * @brief Get the first child node of type `Child` for `node` in the AST that matches
 *        the given predicate.
 *
 * @tparam Child    The type of the child node.
 * @param node      The starting node.
 * @param pred      A boolean predicate than accepts a `const Child&`.
 *
 * @return const Child* Returns the first matching child or `nullptr` if no such child exists.
 */
template <typename Child, typename Predicate, typename = enable_if_t<is_invocable_r_v<bool, Predicate, const Child &>>>
const Child *GetChild(const Stmt &stmt, const Predicate &pred)
{
    for (auto &&child_stmt : stmt.children())
    {
        if (!child_stmt)
        {
            continue;
        }
        if (const auto *child = dyn_cast<Child>(child_stmt);
            child != nullptr && pred(*child))
        {
            return child;
        }
        if (const Child *matching_descendant = GetChild<Child>(*child_stmt, pred);
            matching_descendant != nullptr)
        {
            return matching_descendant;
        }
    }
    return nullptr;
}

template <typename Child>
const Child *GetChild(const Stmt &stmt)
{
    return GetChild<Child>(stmt, [](const Child &) { return true; });
}

template <typename Child, typename Predicate, typename = enable_if_t<is_invocable_r_v<bool, Predicate, const Child &>>>
bool HasChild(const Stmt &stmt, const Predicate &pred)
{
    return GetChild<Child>(stmt, pred) != nullptr;
}

template <typename Child>
bool HasChild(const Stmt &stmt)
{
    return GetChild<Child>(stmt) != nullptr;
}

struct ASTDeallocator
{
    ASTContext &context;

    ASTDeallocator(ASTContext &ctx) : context{ctx} {}

    void operator()(void *p)
    {
        context.Deallocate(p);
    }
};

template <typename T>
using unique_ast_ptr = unique_ptr<T, ASTDeallocator>;

ostream &operator<<(ostream &os, const ValueInfo &value_info);

ostream &operator<<(ostream &os, const CharInfo &char_info)
{
    const auto [value, delim] = char_info;

    if (!isprint(static_cast<unsigned char>(value)))
    {
        os << escape_char;
        const auto old_fill = os.fill('0');
        os << oct << setw(3) << +value;
        os.unsetf(ios_base::oct);
        os.fill(old_fill);
        return os;
    }

    if (value == delim || value == escape_char)
    {
        os << escape_char;
    }
    return os << value;
}

ostream &operator<<(ostream &os, const StructInfo &struct_info)
{
    auto &&[value, type, ast_context, last] = struct_info;
    auto *record_decl = type->getAsCXXRecordDecl();

    const auto base_count = value.getStructNumBases();
    const auto field_count = value.getStructNumFields();

    auto base_iter = record_decl->bases_begin();
    auto base_end = record_decl->bases_end();
    for (unsigned i = 0; i < base_count; ++i)
    {
        const auto &base = value.getStructBase(i);

        // The amount of bases in the type should be the same as the one in the value
        // so we shouldn't get into trouble here...
        if (base_iter != base_end)
        {
            const auto &base_type = base_iter->getType();

            const auto last_base_with_fields = i == base_count - 1 || none_of(next(base_iter), base_end, BaseHasAnyFields);

            os << StructInfo(base, base_type, ast_context,
                             last_base_with_fields && field_count == 0 && last);
            ++base_iter;
        }
        else
        {
            // No point to continue atm.
            break;
        }
    }

    auto field_iter = record_decl->field_begin();
    auto field_end = record_decl->field_end();
    for (unsigned i = 0; i < field_count; ++i)
    {
        const auto &field = value.getStructField(i);

        // The amount of fields in the type should be the same as the one in the value
        // so we shouldn't get into trouble here...
        if (field_iter != field_end)
        {
            const auto &field_type = field_iter->getType();
            os << ValueInfo(field, field_type, ast_context);
            if (!last || i < field_count - 1)
            {
                os << ",";
            }
            ++field_iter;
        }
        else
        {
            // No point to continue atm.
            break;
        }
    }
    return os;
}

ostream &operator<<(ostream &os, const ValueInfo &value_info)
{
    auto &&[value, type, ast_context] = value_info;

    // Print only literal types
    if (!type->isLiteralType(ast_context))
    {
        return os << "<non-literal>";
    }

    // Peel references
    if (type->isReferenceType())
    {
        return os << ValueInfo(value, type->getPointeeType(), ast_context);
    }

    if (type->isFundamentalType())
    {
        if (type->isAnyCharacterType())
        {
            if (type->isCharType())
            {
                // Check that type is not a typedef to make uint8_t print as a number but char as a character.
                // (type == type.getCanonicalType()) // returns false on `char` for some reason
                if (type.getCanonicalType().getAsString() == type.getAsString())
                {
                    return os << char_delim << CharInfo(static_cast<char>(value.getInt().getExtValue()), char_delim) << char_delim;
                }
            }
            else
            {
                return os << type.getCanonicalType().getUnqualifiedType().getAsString() << "(" << value.getAsString(ast_context, type) << ")";
            }
        }
    }
    else
    {
        if ((type->isPointerType() || (type->isArrayType() && !value.isArray())) &&
            type->getPointeeOrArrayElementType()->isAnyCharacterType())
        {
            const auto str = value.getAsString(ast_context, type);
            // content includes the delimiters
            const auto content_begin = str.find(string_delim);
            const auto content_end = str.rfind(string_delim) + 1;
            return os << str.substr(content_begin, content_end - content_begin);
        }
        if (type->isArrayType())
        {
            const auto element_type = type->getAsArrayTypeUnsafe()->getElementType();

            const auto array_size = value.getArrayInitializedElts();

            // Handle char, signed char, unsigned char (regular strings)
            if (element_type->isCharType())
            {
                if (element_type.getCanonicalType().getAsString() == element_type.getAsString())
                {
                    os << string_delim;
                    for (unsigned i = 0; i < array_size; ++i)
                    {
                        os << CharInfo(static_cast<char>(value.getArrayInitializedElt(i).getInt().getExtValue()), string_delim);
                    }
                    return os << string_delim;
                }
            }
            // Handle wchar_t, char8_t, char16_t, char32_t (special encoding strings)
            else if (element_type->isAnyCharacterType())
            {
                os << element_type.getCanonicalType().getUnqualifiedType().getAsString() << "[]";
            }

            os << "(";
            for (unsigned i = 0; i < array_size; ++i)
            {
                os << ValueInfo(value.getArrayInitializedElt(i), element_type, ast_context);
                if (i < array_size - 1)
                {
                    os << ",";
                }
            }
            return os << ")";
        }
        if (type->isRecordType() && value.isStruct())
        {
            const auto record_decl = type->getAsCXXRecordDecl();
            if (!record_decl->getNameAsString().empty())
            {
                os << record_decl->getQualifiedNameAsString();
            }
            return os << "(" << StructInfo(value, type, ast_context, true) << ")";
        }
    }

    // Default for all types that don't require special handling (ie: most `int`s, `float`, ...)
    return os << value.getAsString(ast_context, type);
}

ostream &operator<<(ostream &os, const RecordInfo &record_info)
{
    auto &&[decl, last] = record_info;

    const auto empty = decl->field_empty();

    auto base_end = decl->bases_end();
    for (auto base_iter = decl->bases_begin(); base_iter != base_end; ++base_iter)
    {
        auto next_base = next(base_iter);
        const auto last_base_with_fields = next_base == base_end || none_of(next_base, base_end, BaseHasAnyFields);

        if (base_iter->getType()->isRecordType())
        {
            os << RecordInfo(base_iter->getType()->getAsCXXRecordDecl(),
                             last_base_with_fields && empty && last);
        }
    }

    auto field_end = decl->field_end();
    for (auto field_iter = decl->field_begin(); field_iter != field_end; ++field_iter)
    {
        os << field_iter->getNameAsString();
        if (next(field_iter) != field_end || !last)
        {
            os << ",";
        }
    }
    return os;
}

class ConstantsDumperVisitor : public RecursiveASTVisitor<ConstantsDumperVisitor>
{
public:
    bool VisitEnumDecl(EnumDecl *decl)
    {
        DBG_NOTE(---------------------);
        DBG_NOTE(Enter VisitEnumDecl());

        DBG(decl->getNameAsString());          // bar
        DBG(decl->getQualifiedNameAsString()); // foo::bar
        DBG(decl->getIntegerType().getAsString());
        DBG(decl->isTemplated());

        // Exclude template definitions
        if (decl->isTemplated())
        {
            return true;
        }

        cout << "enum " << decl->getQualifiedNameAsString() << " {" << endl;
        for (auto &&enum_constant_decl : decl->enumerators())
        {
            cout << enum_constant_decl->getQualifiedNameAsString() << OUTPUT_EQ
                 << ValueInfo(APValue(enum_constant_decl->getInitVal()), decl->getIntegerType(), *context)
                 << "," << endl;
        }
        cout << "}" << endl;

        DBG_NOTE(Leave VisitEnumDecl());
        DBG_NOTE(---------------------);

        return true;
    }

    bool VisitVarDecl(VarDecl *decl)
    {
        DBG_NOTE(--------------------);
        DBG_NOTE(Enter VisitVarDecl());

        DBG(decl->getNameAsString());                                               // bar
        DBG(decl->getQualifiedNameAsString());                                      // foo::bar
        DBG(decl->getType().getQualifiers().getAsString());                         // const
        DBG(decl->getType().getCanonicalType().getUnqualifiedType().getAsString()); // int
        DBG(decl->getType().getCanonicalType().getAsString());                      // const int
        DBG(decl->getType().getUnqualifiedType().getAsString());                    // int32_t
        DBG(decl->getType().getAsString());                                         // const int32_t
        DBG(decl->getType()->isFundamentalType());
        DBG(decl->getType()->isRecordType());
        DBG(decl->getType()->isLiteralType(*context));
        DBG(decl->getType()->isArrayType());
        DBG(decl->getType()->isConstantArrayType());
        DBG(decl->getType()->isPointerType());
        DBG(decl->isTemplated());

#ifdef DEBUG_PLUGIN
        if (decl->getType()->isArrayType() || decl->getType()->isPointerType())
        {
            DBG(QualType(decl->getType()->getPointeeOrArrayElementType(), Qualifiers::Const).getAsString());
        }
        if (decl->getType()->isArrayType())
        {
            auto arr_type = decl->getType()->getAsArrayTypeUnsafe();
            DBG(arr_type->getElementType().getAsString());
        }

        if (decl->getType()->isRecordType())
        {
            DBG(decl->getType()->getAsRecordDecl()->getBody());
            DBG(decl->getType()->getAsRecordDecl()->getNameAsString());

            auto *record_decl = decl->getType()->getAsCXXRecordDecl();
            if (record_decl != nullptr && record_decl->hasDefinition())
            {
                DBG(record_decl->isPOD());
                DBG(record_decl->isStandardLayout());
                DBG(record_decl->isCXX11StandardLayout());
                DBG(record_decl->isLiteral());

                DBG(record_decl->getNameAsString());
                DBG(record_decl->getQualifiedNameAsString());
            }
        }
        if (decl->getEvaluatedValue())
        {
            DBG(decl->getEvaluatedValue()->getAsString(*context, decl->getType()));
        }
#endif // DEBUG_PLUGIN

        // Check only literal types
        if (!decl->getType()->isLiteralType(*context))
        {
            DBG_NOTE(Leave VisitVarDecl()[not literal]);
            DBG_NOTE(--------------------);

            return true;
        }

        // Exclude function parameters
        if (decl->isLocalVarDeclOrParm() && !decl->isLocalVarDecl())
        {
            DBG_NOTE(Leave VisitVarDecl()[local parameter]);
            DBG_NOTE(--------------------);

            return true;
        }

        // Make sure there is an initialization for the variable
        if (!decl->hasInit())
        {
            DBG_NOTE(Leave VisitVarDecl()[no init]);
            DBG_NOTE(--------------------);

            return true;
        }

        if (!decl->isConstexpr() && !decl->isUsableInConstantExpressions(*context))
        {
            DBG_NOTE(Leave VisitVarDecl()[not constexpr]);
            DBG_NOTE(--------------------);

            return true;
        }

        if (decl->getEvaluatedValue() == nullptr)
        {
            DBG_NOTE(Leave VisitVarDecl()[no value]);
            DBG_NOTE(--------------------);

            return true;
        }

#ifdef DEBUG_PLUGIN
        if (decl->getType()->isAnyCharacterType())
        {
            DBG(decl->getType()->isCharType());
            DBG(decl->getType()->isWideCharType());
            DBG(decl->getType()->isChar8Type());
            DBG(decl->getType()->isChar16Type());
            DBG(decl->getType()->isChar32Type());
        }
        if (decl->getEvaluatedValue()->isInt())
        {
            DBG(decl->getEvaluatedValue()->getInt().getExtValue());
            DBG(decl->getEvaluatedValue()->getInt().getSExtValue());
            DBG(decl->getEvaluatedValue()->getInt().getZExtValue());
        }
        if (decl->getEvaluatedValue()->isFloat())
        {
            DBG(decl->getEvaluatedValue()->getFloat().convertToFloat());
            DBG(decl->getEvaluatedValue()->getFloat().convertToDouble());
        }
#endif // DEBUG_PLUGIN

        cout << decl->getQualifiedNameAsString() << OUTPUT_EQ
             << ValueInfo(*decl->getEvaluatedValue(), decl->getType(), *context) << endl;

        DBG_NOTE(Leave VisitVarDecl());
        DBG_NOTE(--------------------);
        return true;
    }

#ifdef DEBUG_PLUGIN
    void all_parents(const ast_type_traits::DynTypedNode &node, std::string depth = ""s)
    {
        DBG(depth);
        auto &&parents = context->getParents(node);
        DBG(parents.empty());
        unsigned idx = 0;
        for (auto &&parent : parents)
        {
            auto parent_id = depth + " " + to_string(idx);
            DBG(parent_id);
            DBG(parent.getNodeKind().asStringRef().str());
            all_parents(parent, parent_id);
            ++idx;
        }
    }

    template <typename NodeT>
    void all_parents(const NodeT &node)
    {
        DBG_NOTE(~~~~~~~~~~~~~~~~~~~~~~);
        DBG_NOTE(Traversing all parents);
        all_parents(ast_type_traits::DynTypedNode::create(node));
        DBG_NOTE(~~~~~~~~~~~~~~~~~~~~~~);
    }
#endif // DEBUG_PLUGIN

    bool VisitStringLiteral(StringLiteral *literal)
    {
        DBG_NOTE(--------------------------);
        DBG_NOTE(Enter VisitStringLiteral());

        DBG(literal->getString().str());
        DBG(literal->getType().getAsString());
        DBG(QualType(literal->getType()->getPointeeOrArrayElementType(), 0).getCanonicalType().getAsString());

        DBG(literal->getBeginLoc().isValid());
        DBG(literal->getBeginLoc().isFileID());
        DBG(literal->getBeginLoc().isMacroID());

        auto location = context->getFullLoc(literal->getBeginLoc());

#ifdef DEBUG_PLUGIN
        DBG(location.printToString(context->getSourceManager()));
        DBG(location.isFileID());
        DBG(location.isMacroID());
        DBG(location.isMacroArgExpansion());
        DBG(location.getLineNumber());
        DBG(location.getExpansionLineNumber());
        const FileEntry *file = location.getFileEntry();
        if (file)
        {
            DBG(file->getName().str());
            DBG(file->tryGetRealPathName().str());
        }
#endif // DEBUG_PLUGIN

        DBG(location.isInSystemHeader());

        // Exclude system headers
        if (location.isInSystemHeader())
        {
            DBG_NOTE(Leave VisitStringLiteral()[system header]);
            DBG_NOTE(--------------------------);

            return true;
        }

        auto presumed_location = location.getPresumedLoc();
        DBG(presumed_location.getFilename());
        DBG(presumed_location.getLine());

        DBG(literal->isAscii());

        // Exclude __FILE__
        if (literal->isAscii() && literal->getString() == presumed_location.getFilename())
        {
            DBG_NOTE(Leave VisitStringLiteral()[__FILE__]);
            DBG_NOTE(--------------------------);

            return true;
        }

#ifdef DEBUG_PLUGIN
        all_parents(*literal);
#endif // DEBUG_PLUGIN

        // Only print magic literals, assignment to variable = not magic
        const auto assigned_to_var = HasParent<VarDecl>(*context, *literal,
                                                        [](const VarDecl &decl) { return !decl.isLocalVarDeclOrParm() || decl.isLocalVarDecl(); });
        DBG(assigned_to_var);
        if (assigned_to_var)
        {
#ifdef WARN_POSSIBLE_CONSTEXPR
            auto var = GetParent<VarDecl>(*context, *literal, [](const VarDecl &decl) { return !decl.isLocalVarDeclOrParm() || decl.isLocalVarDecl(); });
            if (!var->isConstexpr() && !var->isUsableInConstantExpressions(*context))
            {
                DiagnosticsEngine &diagEngine = context->getDiagnostics();
                unsigned diagID = diagEngine.getCustomDiagID(DiagnosticsEngine::Warning, "Variable could be marked constexpr");
                auto var_location = var->getLocation();
                diagEngine.Report(var_location, diagID);
            }
#endif // WARN_POSSIBLE_CONSTEXPR

            DBG_NOTE(Leave VisitStringLiteral()[not magic]);
            DBG_NOTE(--------------------------);

            return true;
        }

        // Generate a name: namespaces::func_name()::(literal) or namespaces::(literal) or ::(literal)
        ostringstream name;
        if (const auto *owning_func = GetParent<FunctionDecl>(*context, *literal))
        {
            DBG(owning_func->getNameAsString());
            DBG(owning_func->getQualifiedNameAsString());

            // Exclude __FUNCTION__ / __func__ etc
            if (literal->isAscii() && literal->getString() == owning_func->getNameAsString())
            {
                DBG_NOTE(Leave VisitStringLiteral()[__FUNCTION__]);
                DBG_NOTE(--------------------------);

                return true;
            }
            name << owning_func->getQualifiedNameAsString() << '(';
            const auto param_count = owning_func->getNumParams();
            for (unsigned i = 0; i < param_count; ++i)
            {
                DBG(owning_func->getParamDecl(i)->getType().getAsString());
                name << owning_func->getParamDecl(i)->getType().getAsString();
                if (i < param_count - 1)
                {
                    name << ", ";
                }
            }
            DBG(owning_func->isVariadic());
            if (owning_func->isVariadic())
            {
                if (!owning_func->param_empty())
                {
                    name << ", ";
                }
                name << "...";
            }
            name << ')';

            DBG(owning_func->isCXXClassMember());
            DBG(owning_func->isCXXInstanceMember());
            if (owning_func->isCXXInstanceMember() && isa<CXXMethodDecl>(owning_func))
            {
                const auto *owning_member_func = cast<CXXMethodDecl>(owning_func);

                DBG(owning_member_func->isConst());
                if (owning_member_func->isConst())
                {
                    name << " const";
                }
                DBG(owning_member_func->isVolatile());
                if (owning_member_func->isVolatile())
                {
                    name << " volatile";
                }

                switch (owning_member_func->getRefQualifier())
                {
                case RefQualifierKind::RQ_LValue:
                    name << " &";
                    break;
                case RefQualifierKind::RQ_RValue:
                    name << " &&";
                    break;
                default:
                    break;
                }
            }
        }
        else if (const auto *owning_decl = GetParent<NamedDecl>(*context, *literal))
        {
            DBG(owning_decl->getNameAsString());
            DBG(owning_decl->getQualifiedNameAsString());
            name << owning_decl->getQualifiedNameAsString();
        }
        name << "::(literal)";

        Expr::EvalResult result;
        if (!literal->EvaluateAsConstantExpr(result, Expr::ConstExprUsage::EvaluateForCodeGen, *context))
        {
            DBG_NOTE(Leave VisitStringLiteral()[failed to evaluate]);
            DBG_NOTE(--------------------------);

            return true;
        }
        DBG(result.Val.getAsString(*context, literal->getType()));
        cout << "#literal " << name.str() << OUTPUT_EQ << ValueInfo(result.Val, literal->getType(), *context) << endl;

        DBG_NOTE(Leave VisitStringLiteral());
        DBG_NOTE(--------------------------);
        return true;
    }

    bool VisitFunctionDecl(FunctionDecl *decl)
    {
        DBG_NOTE(-------------------------);
        DBG_NOTE(Enter VisitFunctionDecl());

        DBG(decl->getNameAsString());
        DBG(decl->getQualifiedNameAsString());
        DBG(decl->getType().getAsString());                          // T (...)
        DBG(context->getPointerType(decl->getType()).getAsString()); // T (*)(...)

        // Skip partial definitions
        if (!decl->hasBody())
        {
            DBG_NOTE(Leave VisitFunctionDecl()[no body]);
            DBG_NOTE(-------------------------);

            return true;
        }

        // Exclude template definitions
        if (decl->isTemplated())
        {
            DBG_NOTE(Leave VisitFunctionDecl()[template]);
            DBG_NOTE(-------------------------);

            return true;
        }

        // Exclude non-constexpr functions
        if (!decl->isConstexpr())
        {
            DBG_NOTE(Leave VisitFunctionDecl()[not constexpr]);
            DBG_NOTE(-------------------------);

            return true;
        }

        // Only calculate functions with no parameters
        if (decl->getNumParams() != 0)
        {
            DBG_NOTE(Leave VisitFunctionDecl()[has params]);
            DBG_NOTE(-------------------------);

            return true;
        }

        // Exclude functions that return nothing
        // (Although it's unlikely that a 0-parameter constexpr function that returns nothing will exist)
        auto result_type = decl->getCallResultType();
        if (result_type->isVoidType())
        {
            DBG_NOTE(Leave VisitFunctionDecl()[void]);
            DBG_NOTE(-------------------------);

            return true;
        }

        // Create a CallExpr for a call to the current function
        unique_ast_ptr<DeclRefExpr> decl_ref{
            DeclRefExpr::Create(
                *context,
                decl->getQualifierLoc(),
                decl->getLocation(),
                decl,
                false,
                decl->getLocation(),
                decl->getType(),
                ExprValueKind::VK_LValue,
                decl),
            *context};

        unique_ast_ptr<ImplicitCastExpr> cast_expr{
            ImplicitCastExpr::Create(
                *context,
                context->getPointerType(decl->getType()),
                CastKind::CK_FunctionToPointerDecay,
                decl_ref.get(),
                nullptr, // const CXXCastPath * BasePath
                ExprValueKind::VK_RValue),
            *context};

        unique_ast_ptr<CallExpr> func_call{
            CallExpr::Create(
                *context,
                cast_expr.get(),
                {}, // Empty llvm::ArrayRef<Expr*>
                result_type,
                ExprValueKind::VK_RValue,
                decl->getLocation()),
            *context};

        Expr::EvalResult result;
        if (!func_call->EvaluateAsConstantExpr(result, Expr::ConstExprUsage::EvaluateForCodeGen, *context))
        {
            DBG_NOTE(Leave VisitFunctionDecl()[failed to evaluate]);
            DBG_NOTE(-------------------------);

            return true;
        }
        DBG(result.Val.getAsString(*context, result_type));

        cout << decl->getQualifiedNameAsString() << OUTPUT_EQ << ValueInfo(result.Val, result_type, *context) << endl;

        DBG_NOTE(Leave VisitFunctionDecl());
        DBG_NOTE(-------------------------);
        return true;
    }

    void SetASTContext(ASTContext &new_context)
    {
        context = &new_context;
    }

    ASTContext *context;
};

class ConstantsDumperConsumer : public ASTConsumer
{
public:
    void HandleTranslationUnit(ASTContext &context)
    {
        visitor.SetASTContext(context);
        visitor.TraverseDecl(context.getTranslationUnitDecl());
    }

private:
    ConstantsDumperVisitor visitor;
};

class ConstantsDumperASTAction : public PluginASTAction
{
public:
    virtual unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &Compiler, llvm::StringRef InFile)
    {
        return make_unique<ConstantsDumperConsumer>();
    }

    bool ParseArgs(const CompilerInstance &CI,
                   const vector<string> &args)
    {
        return true;
    }
};

class LiteralTypesDumperVisitor : public RecursiveASTVisitor<LiteralTypesDumperVisitor>
{
public:
    bool VisitCXXRecordDecl(CXXRecordDecl *decl)
    {
        DBG_NOTE(--------------------------);
        DBG_NOTE(Enter VisitCXXRecordDecl());

        DBG(decl->getNameAsString());          // bar
        DBG(decl->getQualifiedNameAsString()); // foo::bar
        DBG(decl->hasDefinition());
        DBG(decl->isLambda());
        DBG(decl->isTemplated());

        if (decl->getNameAsString().empty())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[anonymous]);
            DBG_NOTE(--------------------------);

            return true;
        }

        if (!decl->hasDefinition())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[no definition]);
            DBG_NOTE(--------------------------);

            return true;
        }

        DBG(decl->isLiteral());

        if (decl->isLambda())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[lambda]);
            DBG_NOTE(--------------------------);

            return true;
        }

        if (!decl->isLiteral())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[not literal]);
            DBG_NOTE(--------------------------);

            return true;
        }

#ifdef DEBUG_PLUGIN
        if (decl->getDescribedTemplate())
        {
            DBG(decl->getDescribedTemplate()->getNameAsString());
            DBG(decl->getDescribedTemplate()->getQualifiedNameAsString());
        }

        if (decl->getDescribedClassTemplate())
        {
            DBG(decl->getDescribedClassTemplate()->getNameAsString());
            DBG(decl->getDescribedClassTemplate()->getQualifiedNameAsString());
        }

        for (unsigned i = 0; i < decl->getNumTemplateParameterLists(); ++i)
        {
            DBG(i);
            auto param_list = decl->getTemplateParameterList(i);
            DBG(param_list != nullptr);
            if (param_list)
            {
                DBG(param_list->size());
                for (auto &&param : *param_list)
                {
                    DBG(param->getNameAsString());
                    DBG(param->getQualifiedNameAsString());
                }
            }
        }

        for (auto &&base : decl->bases())
        {
            DBG(base.getType().getQualifiers().getAsString());
            DBG(base.getType().getCanonicalType().getUnqualifiedType().getAsString());
            DBG(base.getType().getCanonicalType().getAsString());
            DBG(base.getType().getUnqualifiedType().getAsString());
            DBG(base.getType().getAsString());
        }

        for (auto &&field : decl->fields())
        {
            DBG(field->getNameAsString());
            DBG(field->getQualifiedNameAsString());
            DBG(field->getType().getQualifiers().getAsString());
            DBG(field->getType().getCanonicalType().getUnqualifiedType().getAsString());
            DBG(field->getType().getCanonicalType().getAsString());
            DBG(field->getType().getUnqualifiedType().getAsString());
            DBG(field->getType().getAsString());
        }
#endif // DEBUG_PLUGIN

        cout << decl->getQualifiedNameAsString() << "{" << RecordInfo(decl, true) << "}" << endl;

        DBG_NOTE(Leave VisitCXXRecordDecl());
        DBG_NOTE(--------------------------);

        return true;
    }
};

class LiteralTypesDumperConsumer : public ASTConsumer
{
public:
    void HandleTranslationUnit(ASTContext &context)
    {
        visitor.TraverseDecl(context.getTranslationUnitDecl());
    }

private:
    LiteralTypesDumperVisitor visitor;
};

class LiteralTypesDumperASTAction : public PluginASTAction
{
public:
    virtual unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &Compiler, llvm::StringRef InFile)
    {
        return make_unique<LiteralTypesDumperConsumer>();
    }

    bool ParseArgs(const CompilerInstance &CI,
                   const vector<string> &args)
    {
        return true;
    }
};
} // namespace

static clang::FrontendPluginRegistry::Add<LiteralTypesDumperASTAction> Y("TypesDumper", "Dumps all class / struct literal types from the code");
static clang::FrontendPluginRegistry::Add<ConstantsDumperASTAction> X("ConstantsDumper", "Dumps all constants and enums from the code");
